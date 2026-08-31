"""Background knowledge ingestion and AI processing tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.database.session import AsyncSessionLocal, engine
from app.infrastructure.events import event_bus
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import Document, KnowledgeSourceType
from app.modules.knowledge.infrastructure.loaders import PDFLoader, TextLoader, URLLoader
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

T = TypeVar("T")


def knowledge_upload_dir() -> Path:
    settings = get_settings()
    path = Path(settings.knowledge_upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _reset_async_resources() -> None:
    """Drop loop-bound pools/clients before/after each Celery asyncio.run()."""
    await engine.dispose()
    await event_bus.close()


def run_async(factory: Callable[[], Awaitable[T]]) -> T:
    """Run an async Celery body on a fresh event loop with clean async resources.

    Celery prefork workers call ``asyncio.run`` per task. The shared SQLAlchemy
    async engine / Redis client keep connections bound to the previous loop,
    which surfaces as ``Future attached to a different loop`` and silently
    kills AI replies / ingestion.
    """

    async def _wrapped() -> T:
        await _reset_async_resources()
        try:
            return await factory()
        finally:
            await _reset_async_resources()

    return asyncio.run(_wrapped())


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
    return run_async(lambda: _run_ingest(document_id))


async def _run_process_ai_message(message_id: str) -> str:
    async with AsyncSessionLocal() as session:
        from app.modules.ai.application.ai_service import AIService

        try:
            run = await AIService(session).process_customer_message(message_id)
            await session.commit()
            return run.id if run else "skipped"
        except Exception:
            await session.rollback()
            logger.exception("AI processing failed for message %s", message_id)
            raise


@celery_app.task(name="app.workers.tasks.process_ai_message", bind=True, max_retries=1)
def process_ai_message(self, message_id: str) -> str:  # type: ignore[no-untyped-def]
    return run_async(lambda: _run_process_ai_message(message_id))
