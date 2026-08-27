"""pgvector similarity retriever — LangChain implementation behind Retriever ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.knowledge.domain.models import Document, DocumentChunk, IngestionStatus, KnowledgeSource
from app.modules.knowledge.infrastructure.embeddings import EmbeddingProvider, get_embedding_provider


@dataclass
class RetrievalHit:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class Retriever(ABC):
    @abstractmethod
    async def search(self, query: str, *, organization_id: str, top_k: int | None = None) -> list[RetrievalHit]:
        raise NotImplementedError

    @abstractmethod
    async def search_with_metadata(
        self, query: str, *, organization_id: str, top_k: int | None = None
    ) -> list[RetrievalHit]:
        raise NotImplementedError


class PgVectorRetriever(Retriever):
    """Org-scoped knowledge retriever.

    Public API stays free of LangChain types. Internally delegates to
    `LangChainPgVectorRetriever` for the LangChain DoD path, while
    `search_pgvector` holds the SQLAlchemy/pgvector query used by that adapter.
    """

    def __init__(
        self,
        db: AsyncSession,
        embedding_provider: EmbeddingProvider | None = None,
        default_top_k: int | None = None,
    ) -> None:
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()
        settings = get_settings()
        self.default_top_k = default_top_k if default_top_k is not None else settings.knowledge_top_k

    async def search(self, query: str, *, organization_id: str, top_k: int | None = None) -> list[RetrievalHit]:
        return await self.search_with_metadata(query, organization_id=organization_id, top_k=top_k)

    async def search_with_metadata(
        self, query: str, *, organization_id: str, top_k: int | None = None
    ) -> list[RetrievalHit]:
        k = top_k or self.default_top_k
        # LangChain retriever path (documents → RetrievalHit)
        from app.modules.knowledge.infrastructure.langchain import LangChainPgVectorRetriever

        lc = LangChainPgVectorRetriever(
            db=self.db,
            organization_id=organization_id,
            embedding_provider=self.embedding_provider,
            top_k=k,
        )
        docs = await lc._aget_relevant_documents(query)
        hits: list[RetrievalHit] = []
        for doc in docs:
            meta = dict(doc.metadata or {})
            hits.append(
                RetrievalHit(
                    chunk_id=str(meta.get("chunk_id") or ""),
                    document_id=str(meta.get("document_id") or ""),
                    title=str(meta.get("title") or ""),
                    content=doc.page_content,
                    score=float(meta.get("score") or 0.0),
                    metadata={m: v for m, v in meta.items() if m not in {"chunk_id", "document_id", "title", "score"}},
                )
            )
        return hits

    async def search_pgvector(
        self, query: str, *, organization_id: str, top_k: int | None = None
    ) -> list[RetrievalHit]:
        """Direct pgvector cosine search (used by the LangChain adapter)."""
        k = top_k or self.default_top_k
        vector = await self.embedding_provider.embed_query(query)
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.metadata_,
                Document.title,
                DocumentChunk.embedding.cosine_distance(vector).label("distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(KnowledgeSource, KnowledgeSource.id == Document.knowledge_source_id)
            .where(
                KnowledgeSource.organization_id == organization_id,
                Document.status == IngestionStatus.COMPLETED,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(DocumentChunk.embedding.cosine_distance(vector))
            .limit(k)
        )
        rows = (await self.db.execute(stmt)).all()
        hits: list[RetrievalHit] = []
        for row in rows:
            distance = float(row.distance) if row.distance is not None else 1.0
            score = max(0.0, 1.0 - distance)
            hits.append(
                RetrievalHit(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    title=row.title,
                    content=row.content,
                    score=score,
                    metadata=row.metadata_ or {},
                )
            )
        return hits
