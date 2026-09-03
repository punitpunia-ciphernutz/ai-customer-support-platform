"""Tests for GET / PATCH / DELETE document and source endpoints."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.application.knowledge_service import KnowledgeService
from app.modules.knowledge.domain.models import (
    Document,
    IngestionStatus,
    KnowledgeSource,
    KnowledgeSourceType,
)
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.workers.tasks import _run_ingest


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.knowledge.infrastructure.embeddings.provider.get_embedding_provider",
        lambda: OfflineSemanticEmbeddingProvider(),
    )


async def _create_text_source_and_doc(
    session, org_id: str, *, content: str = "Test content", title: str = "Test Doc"
) -> tuple[KnowledgeSource, Document]:
    source = KnowledgeSource(
        organization_id=org_id,
        name=f"CRUD Test {uuid.uuid4().hex[:6]}",
        type=KnowledgeSourceType.TEXT,
        status=IngestionStatus.PENDING,
        configuration={},
    )
    session.add(source)
    await session.flush()
    doc = await IngestionService(session, embedding_provider=OfflineSemanticEmbeddingProvider()).create_pending_document(
        source=source, title=title, content=content, metadata={"source_type": "TEXT"}
    )
    await session.commit()
    return source, doc


@pytest.mark.asyncio
async def test_get_document_returns_content() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source, doc = await _create_text_source_and_doc(session, org_id, content="Hello world")

    # Ingest so content is stored
    await _run_ingest(doc.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Document).where(Document.id == doc.id))
        document = result.scalar_one()
        assert document.status == IngestionStatus.COMPLETED
        assert document.content is not None
        assert "Hello world" in document.content


@pytest.mark.asyncio
async def test_update_text_document_resets_for_reingest() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source, doc = await _create_text_source_and_doc(session, org_id, content="Original")

    await _run_ingest(doc.id)

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        service = KnowledgeService(session)
        updated = await service.update_text_document(
            org_id, doc.id, title="Updated Title", content="New content here"
        )
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.content == "New content here"
        assert updated.status == IngestionStatus.PENDING
        assert updated.content_hash is None
        await session.commit()

    # Re-ingest with new content
    await _run_ingest(doc.id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Document).where(Document.id == doc.id))
        document = result.scalar_one()
        assert document.status == IngestionStatus.COMPLETED
        assert "New content here" in (document.content or "")


@pytest.mark.asyncio
async def test_update_rejects_non_text_source() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name=f"URL Source {uuid.uuid4().hex[:6]}",
            type=KnowledgeSourceType.URL,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        doc = Document(
            knowledge_source_id=source.id,
            title="URL Doc",
            source_url="https://example.com",
            status=IngestionStatus.COMPLETED,
        )
        session.add(doc)
        await session.flush()
        doc_id = doc.id
        await session.commit()

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        service = KnowledgeService(session)
        with pytest.raises(ValueError, match="Only TEXT"):
            await service.update_text_document(org_id, doc_id, content="nope")


@pytest.mark.asyncio
async def test_get_document_wrong_org_returns_none() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source, doc = await _create_text_source_and_doc(session, org_id)

    async with AsyncSessionLocal() as session:
        service = KnowledgeService(session)
        result = await service.get_document("00000000-0000-0000-0000-000000000000", doc.id)
        assert result is None


@pytest.mark.asyncio
async def test_delete_source_cascades() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source, doc = await _create_text_source_and_doc(session, org_id)
        source_id = source.id
        doc_id = doc.id

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        deleted = await KnowledgeService(session).delete_source(org_id, source_id)
        assert deleted is True
        await session.commit()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Document).where(Document.id == doc_id))
        assert result.scalar_one_or_none() is None
        result = await session.execute(select(KnowledgeSource).where(KnowledgeSource.id == source_id))
        assert result.scalar_one_or_none() is None
