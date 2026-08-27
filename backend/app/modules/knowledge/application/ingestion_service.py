"""Document ingestion: load → normalize → hash → chunk → embed → store."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.knowledge.domain.models import Document, DocumentChunk, IngestionStatus, KnowledgeSource
from app.modules.knowledge.infrastructure.embeddings import EmbeddingProvider, get_embedding_provider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.parsers import get_default_chunker
from app.modules.knowledge.infrastructure.parsers.normalize import content_hash


class IngestionService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.chunker = get_default_chunker()

    async def create_pending_document(
        self,
        *,
        source: KnowledgeSource,
        title: str,
        source_url: str | None = None,
        content: str | None = None,
        metadata: dict | None = None,
    ) -> Document:
        document = Document(
            knowledge_source_id=source.id,
            title=title,
            source_url=source_url,
            content=content,
            metadata_=metadata or {},
            status=IngestionStatus.PENDING,
        )
        self.db.add(document)
        source.status = IngestionStatus.PENDING
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def ingest_loaded_content(self, document_id: str, loaded: LoadedContent) -> Document:
        """Run the full pipeline for an existing pending/failed document."""
        result = await self.db.execute(
            select(Document)
            .options(selectinload(Document.knowledge_source), selectinload(Document.chunks))
            .where(Document.id == document_id)
        )
        document = result.scalar_one()
        source = document.knowledge_source

        text = loaded.text
        digest = content_hash(text)
        existing = await self.db.execute(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document.id).limit(1)
        )
        if document.content_hash == digest and existing.scalar_one_or_none() is not None:
            document.title = loaded.title or document.title
            document.content = text
            document.source_url = loaded.source_url or document.source_url
            document.status = IngestionStatus.COMPLETED
            document.error_message = None
            source.status = IngestionStatus.COMPLETED
            source.last_synced_at = datetime.now(timezone.utc)
            await self.db.flush()
            return document

        document.status = IngestionStatus.PROCESSING
        source.status = IngestionStatus.PROCESSING
        document.error_message = None
        await self.db.flush()

        try:
            await self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))

            chunk_meta_base = {
                "document_id": document.id,
                "source_id": source.id,
                "source_type": source.type.value,
                "title": loaded.title or document.title,
                "url": loaded.source_url or document.source_url,
                "language": "en",
            }
            if loaded.metadata:
                chunk_meta_base.update({k: v for k, v in loaded.metadata.items() if k not in chunk_meta_base})

            chunks = self.chunker.chunk(text, metadata=chunk_meta_base)
            if not chunks:
                raise ValueError("No content to ingest after normalization")

            vectors = await self.embedding_provider.embed_documents([c.content for c in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                self.db.add(
                    DocumentChunk(
                        document_id=document.id,
                        content=chunk.content,
                        chunk_index=chunk.index,
                        token_count=chunk.token_count,
                        metadata_=chunk.metadata,
                        embedding=vector,
                    )
                )

            document.title = loaded.title or document.title
            document.content = text
            document.content_hash = digest
            document.source_url = loaded.source_url or document.source_url
            document.metadata_ = {**(document.metadata_ or {}), **(loaded.metadata or {})}
            document.status = IngestionStatus.COMPLETED
            document.error_message = None
            source.status = IngestionStatus.COMPLETED
            source.last_synced_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(document)
            return document
        except Exception as exc:  # noqa: BLE001 — persist failure status for UI
            document.status = IngestionStatus.FAILED
            document.error_message = str(exc)[:2000]
            source.status = IngestionStatus.FAILED
            await self.db.flush()
            raise
