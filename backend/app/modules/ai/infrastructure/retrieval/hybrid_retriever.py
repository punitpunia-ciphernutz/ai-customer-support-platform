"""Hybrid semantic + keyword retrieval with legacy merge or RRF fusion."""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.infrastructure.retrieval.fts_search import fts_search
from app.modules.ai.infrastructure.retrieval.query_preparer import QueryPreparer
from app.modules.ai.infrastructure.retrieval.rrf import rrf_fuse
from app.modules.knowledge.domain.models import Document, DocumentChunk, IngestionStatus, KnowledgeSource
from app.modules.knowledge.infrastructure.vectorstore.retriever import PgVectorRetriever, RetrievalHit, Retriever

VALID_RETRIEVAL_MODES = frozenset({"legacy", "hybrid_rrf"})


def _tokenize(query: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]{3,}", query.lower()) if t not in {"the", "and", "for", "how"}]


def normalize_retrieval_mode(mode: str | None) -> str:
    value = (mode or "legacy").strip().lower()
    return value if value in VALID_RETRIEVAL_MODES else "legacy"


class HybridRetriever:
    def __init__(
        self,
        db: AsyncSession,
        *,
        retriever: Retriever | None = None,
        keyword_weight: float | None = None,
        mode: str | None = None,
    ) -> None:
        self.db = db
        self.retriever = retriever or PgVectorRetriever(db)
        self.keyword_weight = keyword_weight if keyword_weight is not None else 0.3
        settings = get_settings()
        self.mode = normalize_retrieval_mode(mode if mode is not None else settings.ai_retrieval_mode)

    async def search(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
        top_k: int | None = None,
        mode: str | None = None,
    ) -> list[RetrievalHit]:
        settings = get_settings()
        retrieval_mode = normalize_retrieval_mode(mode if mode is not None else self.mode)
        query = QueryPreparer.prepare(state)

        if retrieval_mode == "hybrid_rrf":
            return await self._search_rrf(
                query,
                organization_id=organization_id,
                top_k=top_k or settings.ai_rrf_candidate_k,
            )

        k = top_k or settings.ai_retrieval_top_k
        semantic_hits = await self.retriever.search(query, organization_id=organization_id, top_k=k)
        keyword_hits = await self._keyword_search(query, organization_id=organization_id, top_k=k)
        return self._merge_hits(semantic_hits, keyword_hits, top_k=k)

    async def _search_rrf(
        self,
        query: str,
        *,
        organization_id: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        settings = get_settings()
        vector_k = settings.ai_vector_candidate_k
        fts_k = settings.ai_fts_candidate_k
        semantic_hits = await self.retriever.search(
            query, organization_id=organization_id, top_k=vector_k
        )
        fts_hits = await self._fts_search(query, organization_id=organization_id, top_k=fts_k)
        return rrf_fuse(
            [semantic_hits, fts_hits],
            k=settings.ai_rrf_k,
            top_k=top_k,
            list_labels=["semantic", "fts"],
        )

    async def _fts_search(self, query: str, *, organization_id: str, top_k: int) -> list[RetrievalHit]:
        """FTS leg (hybrid_rrf mode; unused by legacy merge)."""
        return await fts_search(self.db, query, organization_id=organization_id, top_k=top_k)

    async def _keyword_search(self, query: str, *, organization_id: str, top_k: int) -> list[RetrievalHit]:
        tokens = _tokenize(query)
        if not tokens:
            return []

        conditions = []
        for token in tokens[:6]:
            pattern = f"%{token}%"
            conditions.append(DocumentChunk.content.ilike(pattern))
            conditions.append(Document.title.ilike(pattern))

        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.content,
                DocumentChunk.metadata_,
                Document.title,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(KnowledgeSource, KnowledgeSource.id == Document.knowledge_source_id)
            .where(
                KnowledgeSource.organization_id == organization_id,
                Document.status == IngestionStatus.COMPLETED,
                or_(*conditions),
            )
            .limit(top_k)
        )
        rows = (await self.db.execute(stmt)).all()
        hits: list[RetrievalHit] = []
        for row in rows:
            content_lower = row.content.lower()
            title_lower = row.title.lower()
            matches = sum(1 for t in tokens if t in content_lower or t in title_lower)
            score = min(1.0, matches / max(len(tokens), 1))
            hits.append(
                RetrievalHit(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    title=row.title,
                    content=row.content,
                    score=score,
                    metadata={"keyword_match": True, **(row.metadata_ or {})},
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    def _merge_hits(
        self,
        semantic: list[RetrievalHit],
        keyword: list[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        merged: dict[str, RetrievalHit] = {}
        kw_weight = self.keyword_weight
        sem_weight = 1.0 - kw_weight

        for hit in semantic:
            merged[hit.chunk_id] = RetrievalHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                title=hit.title,
                content=hit.content,
                score=hit.score * sem_weight,
                metadata={**hit.metadata, "semantic": True},
            )

        for hit in keyword:
            existing = merged.get(hit.chunk_id)
            if existing:
                existing.score = min(1.0, existing.score + hit.score * kw_weight)
                existing.metadata["keyword"] = True
            else:
                merged[hit.chunk_id] = RetrievalHit(
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    title=hit.title,
                    content=hit.content,
                    score=hit.score * kw_weight,
                    metadata={**hit.metadata, "keyword": True},
                )

        ranked = sorted(merged.values(), key=lambda h: h.score, reverse=True)
        return ranked[:top_k]
