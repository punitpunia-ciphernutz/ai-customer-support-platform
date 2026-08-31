"""Celery ingestion task end-to-end (TEXT → COMPLETED → searchable)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import Document, IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider, get_embedding_provider
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever
from app.workers.tasks import _run_ingest


@pytest.mark.asyncio
async def test_celery_ingest_document_text_pipeline() -> None:
    provider = OfflineSemanticEmbeddingProvider()
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name="Celery FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        marker = f"celery-ingest-{uuid.uuid4().hex[:8]}"
        doc = await IngestionService(session, embedding_provider=provider).create_pending_document(
            source=source,
            title="Password Reset",
            content=(
                f"{marker} How do I reset my password? Click Forgot Password on the login page "
                "and check your email for the reset link."
            ),
            metadata={"source_type": "TEXT"},
        )
        document_id = doc.id
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
        hits = await PgVectorRetriever(
            session, embedding_provider=get_embedding_provider()
        ).search(
            marker,
            organization_id=document.knowledge_source.organization_id,
            top_k=5,
        )
        assert any(h.document_id == document_id for h in hits)
