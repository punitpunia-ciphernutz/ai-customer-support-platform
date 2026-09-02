"""Day 4 Phase 3 — hybrid retrieval and relevance threshold."""

from app.modules.ai.domain.schemas import IntentLabel, RetrievedDocument, SupportAgentState
from app.modules.ai.infrastructure.retrieval.query_preparer import QueryPreparer
from app.modules.ai.infrastructure.retrieval.relevance_gate import RelevanceGate


def test_query_preparer_enriches_account_access() -> None:
    state = SupportAgentState(
        user_message="I cannot sign in",
        intent=IntentLabel.ACCOUNT_ACCESS,
    )
    prepared = QueryPreparer.prepare(state)
    assert "password" in prepared.lower()


def test_relevance_gate_fails_empty_docs() -> None:
    result = RelevanceGate.evaluate([], threshold=0.35, require_knowledge=True)
    assert not result.passed
    assert "No sufficiently relevant" in (result.reason or "")


def test_relevance_gate_passes_high_score() -> None:
    docs = [
        RetrievedDocument(document_id="1", title="Guide", content="reset password", score=0.92),
    ]
    result = RelevanceGate.evaluate(docs, threshold=0.35, require_knowledge=True)
    assert result.passed
    assert result.top_score == 0.92


def test_relevance_gate_fails_low_score() -> None:
    docs = [
        RetrievedDocument(document_id="1", title="Unrelated", content="weather", score=0.1),
    ]
    result = RelevanceGate.evaluate(docs, threshold=0.35, require_knowledge=True)
    assert not result.passed
