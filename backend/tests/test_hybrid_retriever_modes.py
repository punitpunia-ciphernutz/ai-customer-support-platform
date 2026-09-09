"""HybridRetriever legacy vs hybrid_rrf mode isolation."""

from unittest.mock import AsyncMock

import pytest

from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever, normalize_retrieval_mode
from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit


def _hit(cid: str, score: float) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=cid,
        document_id=f"doc-{cid}",
        title=cid,
        content=f"body {cid}",
        score=score,
        metadata={},
    )


def test_normalize_retrieval_mode() -> None:
    assert normalize_retrieval_mode("legacy") == "legacy"
    assert normalize_retrieval_mode("hybrid_rrf") == "hybrid_rrf"
    assert normalize_retrieval_mode("HYBRID_RRF") == "hybrid_rrf"
    assert normalize_retrieval_mode("nope") == "legacy"
    assert normalize_retrieval_mode(None) == "legacy"


@pytest.mark.asyncio
async def test_legacy_mode_uses_weighted_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_RETRIEVAL_MODE", "legacy")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=[_hit("s1", 1.0), _hit("both", 0.8)])

    hybrid = HybridRetriever(db=AsyncMock(), retriever=retriever, keyword_weight=0.3, mode="legacy")

    async def fake_keyword(query: str, *, organization_id: str, top_k: int):
        return [_hit("k1", 1.0), _hit("both", 1.0)]

    hybrid._keyword_search = fake_keyword  # type: ignore[method-assign]
    hybrid._fts_search = AsyncMock(return_value=[_hit("fts1", 0.9)])  # type: ignore[method-assign]

    state = SupportAgentState(user_message="reset password")
    hits = await hybrid.search(state, organization_id="org", top_k=10, mode="legacy")

    hybrid._fts_search.assert_not_awaited()
    ids = [h.chunk_id for h in hits]
    assert "both" in ids
    both = next(h for h in hits if h.chunk_id == "both")
    # semantic 0.8 * 0.7 + keyword 1.0 * 0.3 = 0.56 + 0.3 = 0.86
    assert both.score == pytest.approx(0.86)
    assert both.metadata.get("semantic") is True
    assert both.metadata.get("keyword") is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_hybrid_rrf_mode_uses_rrf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_RETRIEVAL_MODE", "hybrid_rrf")
    monkeypatch.setenv("AI_VECTOR_CANDIDATE_K", "5")
    monkeypatch.setenv("AI_FTS_CANDIDATE_K", "5")
    monkeypatch.setenv("AI_RRF_CANDIDATE_K", "3")
    monkeypatch.setenv("AI_RRF_K", "60")
    from app.config.settings import get_settings

    get_settings.cache_clear()

    retriever = AsyncMock()
    retriever.search = AsyncMock(return_value=[_hit("a", 0.9), _hit("b", 0.5)])

    hybrid = HybridRetriever(db=AsyncMock(), retriever=retriever, mode="hybrid_rrf")
    hybrid._fts_search = AsyncMock(return_value=[_hit("b", 0.8), _hit("c", 0.7)])  # type: ignore[method-assign]
    hybrid._keyword_search = AsyncMock(return_value=[_hit("k", 1.0)])  # type: ignore[method-assign]

    state = SupportAgentState(user_message="AUTH-401")
    hits = await hybrid.search(state, organization_id="org", mode="hybrid_rrf")

    hybrid._keyword_search.assert_not_awaited()
    hybrid._fts_search.assert_awaited()
    assert hits[0].chunk_id == "b"
    assert hits[0].metadata.get("rrf_rank") == 1
    assert hits[0].metadata.get("semantic") is True
    assert hits[0].metadata.get("fts") is True
    assert len(hits) <= 3
    get_settings.cache_clear()
