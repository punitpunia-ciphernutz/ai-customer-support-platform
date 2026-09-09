"""Unit tests for Reciprocal Rank Fusion."""

from app.modules.ai.infrastructure.retrieval.rrf import rrf_fuse
from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit


def _hit(cid: str, score: float = 1.0) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=cid,
        document_id=f"doc-{cid}",
        title=cid,
        content=f"content {cid}",
        score=score,
        metadata={},
    )


def test_rrf_overlap_promotes_shared_docs() -> None:
    vector = [_hit("a"), _hit("b"), _hit("c")]
    fts = [_hit("b"), _hit("d"), _hit("a")]
    fused = rrf_fuse([vector, fts], k=60, top_k=10, list_labels=["semantic", "fts"])
    assert fused[0].chunk_id in {"a", "b"}
    # Both a and b appear in both lists → higher than single-list c/d
    top_ids = {h.chunk_id for h in fused[:2]}
    assert top_ids == {"a", "b"}
    assert fused[0].metadata["rrf_rank"] == 1
    assert "rrf_score" in fused[0].metadata


def test_rrf_disjoint_lists() -> None:
    vector = [_hit("v1"), _hit("v2")]
    fts = [_hit("f1"), _hit("f2")]
    fused = rrf_fuse([vector, fts], k=60, top_k=4, list_labels=["semantic", "fts"])
    assert len(fused) == 4
    assert {h.chunk_id for h in fused} == {"v1", "v2", "f1", "f2"}
    # First of each list should outrank seconds (same k+rank formula)
    assert fused[0].chunk_id in {"v1", "f1"}


def test_rrf_stable_ties_by_chunk_id() -> None:
    # Identical single-list ranks → equal RRF; tie-break by chunk_id
    left = [_hit("b"), _hit("a")]
    right: list[RetrievalHit] = []
    fused = rrf_fuse([left, right], k=60, top_k=2)
    assert [h.chunk_id for h in fused] == ["b", "a"]


def test_rrf_k_effect() -> None:
    vector = [_hit("only_vector")]
    fts = [_hit("only_fts"), _hit("shared")]
    vector2 = [_hit("shared"), _hit("only_vector")]
    small_k = rrf_fuse([vector2, fts], k=1, top_k=3)
    large_k = rrf_fuse([vector2, fts], k=1000, top_k=3)
    assert small_k[0].chunk_id == "shared"
    assert large_k[0].chunk_id == "shared"
    # Larger k compresses score gaps but ranking of shared stays first
    assert small_k[0].score > large_k[0].score


def test_rrf_top_k_truncation() -> None:
    hits = [[_hit(str(i)) for i in range(5)]]
    fused = rrf_fuse(hits, k=60, top_k=2)
    assert len(fused) == 2
