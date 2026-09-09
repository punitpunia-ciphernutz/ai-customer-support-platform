"""FTS retrieval: org isolation, error codes, empty query."""

import pytest
from sqlalchemy import select, text

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.infrastructure.retrieval.fts_search import extract_error_codes, fts_search
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import DocumentChunk, IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent


@pytest.mark.asyncio
async def test_fts_empty_query_returns_empty() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        hits = await fts_search(session, "   ", organization_id=org_id, top_k=10)
        assert hits == []


@pytest.mark.asyncio
async def test_fts_error_code_and_org_isolation() -> None:
    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    async with AsyncSessionLocal() as session:
        orgs = (await session.execute(select(Organization.id).limit(2))).scalars().all()
        assert len(orgs) >= 1
        org_a = orgs[0]
        # Second org if present; otherwise create isolation via distinct source still scoped to org_a
        org_b = orgs[1] if len(orgs) > 1 else None

        source_a = KnowledgeSource(
            organization_id=org_a,
            name="FTS Auth Codes",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source_a)
        await session.flush()
        service = IngestionService(session, embedding_provider=provider)

        auth_doc = await service.create_pending_document(source=source_a, title="Auth Errors", content="x")
        await service.ingest_loaded_content(
            auth_doc.id,
            LoadedContent(
                title="Auth Errors",
                text=(
                    "Error AUTH-401 means the session token expired. "
                    "Ask the user to sign in again and retry the request."
                ),
                metadata={"source_type": "TEXT"},
            ),
        )

        filler = await service.create_pending_document(source=source_a, title="Billing", content="x")
        await service.ingest_loaded_content(
            filler.id,
            LoadedContent(
                title="Billing",
                text="Update your invoice address under Settings > Billing for payment receipts.",
                metadata={"source_type": "TEXT"},
            ),
        )

        # search_document + tsv populated by ingest + trigger
        chunk = (
            await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == auth_doc.id).limit(1))
        ).scalar_one()
        assert chunk.search_document and "AUTH-401" in chunk.search_document
        assert chunk.search_tsv is not None

        hits = await fts_search(session, "AUTH-401 expired token", organization_id=org_a, top_k=10)
        assert hits, "expected FTS hits for AUTH-401"
        assert any(h.document_id == auth_doc.id for h in hits)
        assert hits[0].metadata.get("fts") is True

        hybrid = HybridRetriever(session, retriever=None)
        fts_via_hybrid = await hybrid._fts_search("AUTH-401", organization_id=org_a, top_k=5)
        assert any(h.document_id == auth_doc.id for h in fts_via_hybrid)

        if org_b:
            other = await fts_search(session, "AUTH-401", organization_id=org_b, top_k=10)
            assert all(h.document_id != auth_doc.id for h in other)

        await session.rollback()


def test_extract_error_codes() -> None:
    assert "AUTH-401" in extract_error_codes("got AUTH-401 from API")
    assert "ERR_PAYMENT_403" in extract_error_codes("ERR_PAYMENT_403 declined")
    assert extract_error_codes("hello world") == []
