"""Relevance evaluation / reranking for retrieved knowledge chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.modules.ai.infrastructure.llm.providers import LLMProvider
from app.modules.ai.prompts import render_rerank_prompt
from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit


class RelevanceScore(BaseModel):
    relevance: float = Field(ge=0.0, le=1.0)


@dataclass
class RankedHit:
    hit: RetrievalHit
    relevance: float


class Reranker:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    async def rank(self, query: str, hits: list[RetrievalHit], *, top_k: int = 5) -> list[RankedHit]:
        if not hits:
            return []

        ranked: list[RankedHit] = []
        for hit in hits:
            relevance = await self._score(query, hit)
            ranked.append(RankedHit(hit=hit, relevance=relevance))

        ranked.sort(key=lambda r: r.relevance, reverse=True)
        return ranked[:top_k]

    async def _score(self, query: str, hit: RetrievalHit) -> float:
        if self.llm is not None:
            try:
                from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider

                if not isinstance(self.llm, EchoLLMProvider):
                    prompt = render_rerank_prompt(query, hit.title, hit.content)
                    result = await self.llm.structured_output(prompt, RelevanceScore)
                    return float(result.relevance)
            except Exception:
                pass
        return _heuristic_score(query, hit)


def _heuristic_score(query: str, hit: RetrievalHit) -> float:
    """Blend vector similarity with token overlap for offline/tests."""
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    text = f"{hit.title} {hit.content}".lower()
    t_tokens = set(re.findall(r"[a-z0-9]+", text))
    overlap = len(q_tokens & t_tokens) / max(len(q_tokens), 1)
    vector = max(0.0, min(1.0, hit.score))
    return min(1.0, 0.55 * vector + 0.45 * overlap)


def aggregate_retrieval_score(ranked: list[RankedHit]) -> float:
    if not ranked:
        return 0.0
    scores = [r.relevance for r in ranked]
    return max(scores) * 0.6 + (sum(scores) / len(scores)) * 0.4
