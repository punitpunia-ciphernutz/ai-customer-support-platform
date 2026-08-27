"""Background knowledge ingestion tasks."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import Document, KnowledgeSourceType
from app.modules.knowledge.infrastructure.loaders import PDFLoader, TextLoader, URLLoader
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def knowledge_upload_dir() -> Path:
    settings = get_settings()
    path = Path(settings.knowledge_upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _run_ingest(document_id: str) -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Document)
            .options(selectinload(Document.knowledge_source))
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        source = document.knowledge_source
        meta = document.metadata_ or {}

        try:
            if source.type == KnowledgeSourceType.TEXT:
                loaded = await TextLoader(document.content or "", title=document.title).load()
            elif source.type == KnowledgeSourceType.URL:
                url = document.source_url or meta.get("url")
                if not url:
                    raise ValueError("URL document missing source_url")
                loaded = await URLLoader(str(url), title=document.title).load()
            elif source.type == KnowledgeSourceType.PDF:
                pdf_path = knowledge_upload_dir() / f"{document_id}.pdf"
                if not pdf_path.exists():
                    raise ValueError(f"PDF file missing for document {document_id}")
                loaded = await PDFLoader(pdf_path.read_bytes(), title=document.title).load()
            else:
                raise ValueError(f"Unsupported source type: {source.type}")

            await IngestionService(session).ingest_loaded_content(document_id, loaded)
            await session.commit()
            return document_id
        except Exception:
            await session.commit()  # persist FAILED status flushed by IngestionService
            logger.exception("Ingestion failed for document %s", document_id)
            raise


@celery_app.task(name="app.workers.tasks.ingest_document", bind=True, max_retries=1)
def ingest_document(self, document_id: str) -> str:  # type: ignore[no-untyped-def]
    return asyncio.run(_run_ingest(document_id))
