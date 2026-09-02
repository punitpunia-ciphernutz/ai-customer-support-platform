"""Relevance threshold gate after reranking."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai.domain.schemas import RetrievedDocument


@dataclass
class RelevanceGateResult:
    passed: bool
    reason: str | None = None
    top_score: float = 0.0


class RelevanceGate:
    @staticmethod
    def evaluate(
        docs: list[RetrievedDocument],
        *,
        threshold: float,
        require_knowledge: bool = True,
    ) -> RelevanceGateResult:
        if not docs:
            if require_knowledge:
                return RelevanceGateResult(
                    passed=False,
                    reason="No sufficiently relevant knowledge found.",
                    top_score=0.0,
                )
            return RelevanceGateResult(passed=True, top_score=0.0)

        top_score = max(d.score for d in docs)
        if top_score < threshold:
            return RelevanceGateResult(
                passed=False,
                reason=f"Top relevance score {top_score:.2f} below threshold {threshold:.2f}.",
                top_score=top_score,
            )
        return RelevanceGateResult(passed=True, top_score=top_score)
