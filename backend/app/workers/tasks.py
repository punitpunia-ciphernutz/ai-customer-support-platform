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


async def _run_process_missed_chats() -> int:
    async with AsyncSessionLocal() as session:
        from app.modules.ai.application.missed_chat_service import MissedChatService

        try:
            count = await MissedChatService(session).process_timeouts()
            await session.commit()
            return count
        except Exception:
            await session.rollback()
            logger.exception("Missed chat timeout processing failed")
            raise


async def _run_process_ai_response_timeouts() -> int:
    async with AsyncSessionLocal() as session:
        from app.modules.ai.application.ai_response_timeout_service import AIResponseTimeoutService

        try:
            count = await AIResponseTimeoutService(session).process_timeouts()
            await session.commit()
            return count
        except Exception:
            await session.rollback()
            logger.exception("AI response timeout processing failed")
            raise


@celery_app.task(name="app.workers.tasks.process_missed_chats")
def process_missed_chats() -> int:  # type: ignore[no-untyped-def]
    return run_async(_run_process_missed_chats)


@celery_app.task(name="app.workers.tasks.process_ai_response_timeouts")
def process_ai_response_timeouts() -> int:  # type: ignore[no-untyped-def]
    return run_async(_run_process_ai_response_timeouts)


async def _run_check_missed_chat(conversation_id: str, organization_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        from app.modules.ai.application.missed_chat_service import MissedChatService

        try:
            handled = await MissedChatService(session).check_conversation(conversation_id, organization_id)
            await session.commit()
            return handled
        except Exception:
            await session.rollback()
            logger.exception("Missed chat check failed for conversation %s", conversation_id)
            raise


@celery_app.task(name="app.workers.tasks.check_missed_chat")
def check_missed_chat(conversation_id: str, organization_id: str) -> bool:  # type: ignore[no-untyped-def]
    return run_async(lambda: _run_check_missed_chat(conversation_id, organization_id))


async def _run_process_sla_breaches() -> int:
    async with AsyncSessionLocal() as session:
        from app.infrastructure.database.models import Organization
        from app.modules.sla.application.service import SLAService

        try:
            org_ids = list((await session.execute(select(Organization.id))).scalars().all())
            total = 0
            for org_id in org_ids:
                total += await SLAService(session).check_breaches(org_id)
            await session.commit()
            return total
        except Exception:
            await session.rollback()
            logger.exception("SLA breach processing failed")
            raise


@celery_app.task(name="app.workers.tasks.process_sla_breaches")
def process_sla_breaches() -> int:  # type: ignore[no-untyped-def]
    return run_async(_run_process_sla_breaches)


async def _run_execute_automation_event(
    organization_id: str,
    event_name: str,
    payload: dict,
    execution_depth: int = 0,
    trigger_event_id: str | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        from app.modules.automation.application.execution_service import ExecutionService

        try:
            results = await ExecutionService(session).execute_for_event(
                organization_id=organization_id,
                event_name=event_name,
                payload=payload,
                execution_depth=execution_depth,
                trigger_event_id=trigger_event_id,
            )
            await session.commit()
            return len(results)
        except Exception:
            await session.rollback()
            logger.exception("Automation execution task failed for %s", event_name)
            raise


@celery_app.task(name="app.workers.tasks.execute_automation_event")
def execute_automation_event(  # type: ignore[no-untyped-def]
    organization_id: str,
    event_name: str,
    payload: dict,
    execution_depth: int = 0,
    trigger_event_id: str | None = None,
) -> int:
    return run_async(
        lambda: _run_execute_automation_event(
            organization_id,
            event_name,
            payload,
            execution_depth,
            trigger_event_id,
        )
    )
