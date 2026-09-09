"""Reciprocal Rank Fusion (RRF) for multi-list retrieval."""

from __future__ import annotations

from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit


def rrf_fuse(
    ranked_lists: list[list[RetrievalHit]],
    *,
    k: int = 60,
    top_k: int | None = None,
    list_labels: list[str] | None = None,
) -> list[RetrievalHit]:
    """Fuse ranked hit lists with RRF: score(d) = Σ 1 / (k + rank_i(d)).

    Ranks are 1-based within each list. Duplicate chunk_ids accumulate score;
    content/metadata are taken from the first occurrence, with fusion flags merged.
    """
    if k < 1:
        raise ValueError("k must be >= 1")

    labels = list_labels or [f"list_{i}" for i in range(len(ranked_lists))]
    scores: dict[str, float] = {}
    best: dict[str, RetrievalHit] = {}
    per_list_ranks: dict[str, dict[str, int]] = {}

    for list_idx, hits in enumerate(ranked_lists):
        label = labels[list_idx] if list_idx < len(labels) else f"list_{list_idx}"
        for rank, hit in enumerate(hits, start=1):
            cid = hit.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            ranks = per_list_ranks.setdefault(cid, {})
            # Keep best (lowest) rank if the same list somehow duplicates
            prev = ranks.get(label)
            if prev is None or rank < prev:
                ranks[label] = rank
            if cid not in best:
                best[cid] = hit

    ordered = sorted(scores.keys(), key=lambda cid: (-scores[cid], cid))
    if top_k is not None:
        ordered = ordered[: max(0, top_k)]

    fused: list[RetrievalHit] = []
    for rrf_rank, cid in enumerate(ordered, start=1):
        src = best[cid]
        meta = dict(src.metadata or {})
        ranks = per_list_ranks.get(cid, {})
        for label, rank in ranks.items():
            meta[label] = True
            meta[f"{label}_rank"] = rank
        meta["rrf_rank"] = rrf_rank
        meta["rrf_score"] = scores[cid]
        fused.append(
            RetrievalHit(
                chunk_id=src.chunk_id,
                document_id=src.document_id,
                title=src.title,
                content=src.content,
                score=scores[cid],
                metadata=meta,
            )
        )
    return fused
