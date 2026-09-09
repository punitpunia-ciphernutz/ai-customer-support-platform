"""Golden retrieval queries: semantic + error-code + distractor (legacy vs RRF)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever


async def _seed_golden_kb(session, org_id: str, provider: OfflineSemanticEmbeddingProvider):
    source = KnowledgeSource(
        organization_id=org_id,
        name="Golden Hybrid KB",
        type=KnowledgeSourceType.TEXT,
        status=IngestionStatus.PENDING,
        configuration={},
    )
    session.add(source)
    await session.flush()
    service = IngestionService(session, embedding_provider=provider)

    pwd = await service.create_pending_document(source=source, title="Password Reset", content="x")
    await service.ingest_loaded_content(
        pwd.id,
        LoadedContent(
            title="Password Reset",
            text=(
                "How do I reset my password? Use the Forgot Password link on the login page "
                "and follow the email instructions to regain account access."
            ),
            metadata={"source_type": "TEXT", "fixture": "password"},
        ),
    )

    auth = await service.create_pending_document(source=source, title="AUTH-401 Errors", content="x")
    await service.ingest_loaded_content(
        auth.id,
        LoadedContent(
            title="AUTH-401 Errors",
            text=(
                "Error code AUTH-401 means the session token expired or is invalid. "
                "Ask the customer to sign in again. Do not confuse with billing failures."
            ),
            metadata={"source_type": "TEXT", "fixture": "auth"},
        ),
    )

    filler = await service.create_pending_document(source=source, title="Office Plants", content="x")
    await service.ingest_loaded_content(
        filler.id,
        LoadedContent(
            title="Office Plants",
            text=(
                "Our lobby has ferns and succulents. Water weekly. This document is unrelated "
                "to authentication, passwords, or payments."
            ),
            metadata={"source_type": "TEXT", "fixture": "filler"},
        ),
    )
    return {"password": pwd.id, "auth": auth.id, "filler": filler.id}


@pytest.mark.asyncio
async def test_golden_legacy_and_rrf_retrieval() -> None:
    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        ids = await _seed_golden_kb(session, org_id, provider)
        retriever = PgVectorRetriever(session, embedding_provider=provider)

        hybrid_legacy = HybridRetriever(session, retriever=retriever, keyword_weight=0.3, mode="legacy")
        hybrid_rrf = HybridRetriever(session, retriever=retriever, mode="hybrid_rrf")

        # Semantic: password reset should beat filler
        sem_state = SupportAgentState(user_message="How do I reset my password?")
        legacy_sem = await hybrid_legacy.search(sem_state, organization_id=org_id, top_k=10, mode="legacy")
        rrf_sem = await hybrid_rrf.search(sem_state, organization_id=org_id, top_k=20, mode="hybrid_rrf")

        assert any(h.document_id == ids["password"] for h in legacy_sem)
        assert any(h.document_id == ids["password"] for h in rrf_sem)
        legacy_pwd_rank = next(i for i, h in enumerate(legacy_sem) if h.document_id == ids["password"])
        legacy_filler_rank = next(
            (i for i, h in enumerate(legacy_sem) if h.document_id == ids["filler"]), 999
        )
        assert legacy_pwd_rank < legacy_filler_rank

        # Error code: AUTH-401 must surface under RRF (FTS leg); legacy ILIKE may also hit
        code_state = SupportAgentState(user_message="What does AUTH-401 mean?")
        rrf_code = await hybrid_rrf.search(code_state, organization_id=org_id, top_k=20, mode="hybrid_rrf")
        legacy_code = await hybrid_legacy.search(code_state, organization_id=org_id, top_k=10, mode="legacy")

        assert any(h.document_id == ids["auth"] for h in rrf_code), "RRF must retrieve AUTH-401 doc"
        rrf_auth_rank = next(i for i, h in enumerate(rrf_code) if h.document_id == ids["auth"])
        assert rrf_auth_rank < 5

        # RRF should not rank worse than legacy for exact-code queries when both find it
        if any(h.document_id == ids["auth"] for h in legacy_code):
            legacy_auth_rank = next(i for i, h in enumerate(legacy_code) if h.document_id == ids["auth"])
            assert rrf_auth_rank <= legacy_auth_rank + 2

        # Org isolation: empty query / wrong org shape already covered elsewhere
        await session.rollback()


@pytest.mark.asyncio
async def test_golden_default_mode_is_hybrid_rrf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_RETRIEVAL_MODE", raising=False)
    from app.config.settings import get_settings

    get_settings.cache_clear()
    assert get_settings().ai_retrieval_mode == "hybrid_rrf"
    get_settings.cache_clear()
