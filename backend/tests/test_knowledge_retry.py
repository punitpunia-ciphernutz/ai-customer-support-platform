"""Retry ingestion for stuck PENDING / FAILED knowledge documents."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import Document, IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.workers.tasks import _run_ingest


@pytest.mark.asyncio
async def test_prepare_retry_requeues_stuck_pending_document() -> None:
    provider = OfflineSemanticEmbeddingProvider()
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name=f"Retry FAQ {uuid.uuid4().hex[:6]}",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        doc = await IngestionService(session, embedding_provider=provider).create_pending_document(
            source=source,
            title="Stuck doc",
            content="How do I reset my password? Use the forgot password link.",
            metadata={"source_type": "TEXT"},
        )
        document_id = doc.id
        await session.commit()

    async with AsyncSessionLocal() as session:
        ingestion = IngestionService(session, embedding_provider=provider)
        result = await session.execute(select(Document).where(Document.id == document_id))
        stuck = result.scalar_one()
        assert stuck.status == IngestionStatus.PENDING
        retried = await ingestion.prepare_retry(stuck)
        assert retried.status == IngestionStatus.PENDING
        assert retried.error_message is None
        await session.commit()

    result_id = await _run_ingest(document_id)
    assert result_id == document_id

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Document)
            .options(selectinload(Document.knowledge_source))
            .where(Document.id == document_id)
        )
        document = result.scalar_one()
        assert document.status == IngestionStatus.COMPLETED
        assert document.knowledge_source.status == IngestionStatus.COMPLETED


@pytest.mark.asyncio
async def test_prepare_retry_rejects_completed_document() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name=f"Done FAQ {uuid.uuid4().hex[:6]}",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.COMPLETED,
            configuration={},
        )
        session.add(source)
        await session.flush()
        doc = Document(
            knowledge_source_id=source.id,
            title="Done",
            content="content",
            status=IngestionStatus.COMPLETED,
        )
        session.add(doc)
        await session.flush()

        with pytest.raises(ValueError, match="not retryable"):
            await IngestionService(session).prepare_retry(doc)
