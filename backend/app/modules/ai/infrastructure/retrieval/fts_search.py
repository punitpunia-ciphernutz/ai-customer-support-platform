"""PostgreSQL full-text search helpers for document chunks.

Uses the `simple` text search config so support error codes / IDs
(e.g. AUTH-401, ERR_PAYMENT_403) are not over-stemmed by `english`.
"""

from __future__ import annotations

import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.domain.models import Document, DocumentChunk, IngestionStatus, KnowledgeSource
from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit

# Error / ticket style tokens that benefit from exact / phrase matching.
_ERROR_CODE_RE = re.compile(r"\b([A-Za-z]+[-_][A-Za-z0-9_-]+)\b")


def build_fts_query_string(query: str) -> str:
    """Normalize user text for websearch_to_tsquery('simple', ...)."""
    return " ".join((query or "").strip().split())


def extract_error_codes(query: str) -> list[str]:
    return [m.group(1) for m in _ERROR_CODE_RE.finditer(query or "")]


def build_search_document(*, title: str | None, content: str) -> str:
    return f"{title or ''} {content or ''}".strip()


async def fts_search(
    db: AsyncSession,
    query: str,
    *,
    organization_id: str,
    top_k: int,
) -> list[RetrievalHit]:
    """Org-scoped FTS over document_chunks.search_tsv (COMPLETED docs only)."""
    q = build_fts_query_string(query)
    if not q or top_k <= 0:
        return []

    ts_query = func.websearch_to_tsquery("simple", q)
    rank = func.ts_rank_cd(DocumentChunk.search_tsv, ts_query).label("rank")

    match_clauses = [DocumentChunk.search_tsv.op("@@")(ts_query)]
    for code in extract_error_codes(q)[:4]:
        match_clauses.append(DocumentChunk.search_tsv.op("@@")(func.phraseto_tsquery("simple", code)))
        match_clauses.append(DocumentChunk.search_document.ilike(f"%{code}%"))

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.content,
            DocumentChunk.metadata_,
            Document.title,
            rank,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(KnowledgeSource, KnowledgeSource.id == Document.knowledge_source_id)
        .where(
            KnowledgeSource.organization_id == organization_id,
            Document.status == IngestionStatus.COMPLETED,
            DocumentChunk.search_tsv.is_not(None),
            or_(*match_clauses),
        )
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(top_k)
    )

    rows = (await db.execute(stmt)).all()
    hits: list[RetrievalHit] = []
    for row in rows:
        score = float(row.rank) if row.rank is not None else 0.0
        hits.append(
            RetrievalHit(
                chunk_id=row.id,
                document_id=row.document_id,
                title=row.title,
                content=row.content,
                score=score,
                metadata={"fts": True, **(row.metadata_ or {})},
            )
        )
    return hits
