# Hybrid Search — Schema Notes

**Status:** Phases 0–5 implemented; **default mode = `hybrid_rrf`** (`legacy` = optional rollback)  
**Plan:** [`docs/hybrid-search-implementation-plan.md`](../hybrid-search-implementation-plan.md)  
**Changes / mode comparison:** [`docs/hybrid-search-changes.md`](../hybrid-search-changes.md)

## Purpose

Additive PostgreSQL indexes and FTS columns for production-grade hybrid retrieval:

1. **HNSW** on `document_chunks.embedding` (ANN cosine) — Phase 1 ✅
2. **FTS** (`search_document` / `search_tsv` + GIN) — Phase 2 ✅
3. Application fusion via **RRF** (`ai_retrieval_mode=hybrid_rrf`) — Phase 3 ✅
4. Golden / benchmark validation — Phase 4 ✅
5. Optional org `retrieval_mode` — Phase 5 ✅ (often unused for single-tenant)

Legacy path (exact cosine + ILIKE + weighted merge) remains available as **rollback**.

## Mode difference (quick)

| Mode | Keyword | Fusion | Candidates into reranker | Role |
|------|---------|--------|--------------------------|------|
| **`hybrid_rrf` (default)** | FTS (`simple` + GIN) | RRF ranks | `AI_RRF_CANDIDATE_K` (40) | Production default |
| **`legacy` (optional)** | ILIKE tokens | Weighted score blend | `AI_RETRIEVAL_TOP_K` (10) | Emergency rollback |

Both share: pgvector (± HNSW), same org filters, same Reranker + RelevanceGate + LLM.

## Settings (env)

| Key | Default | Notes |
|-----|---------|--------|
| `AI_RETRIEVAL_MODE` | **`hybrid_rrf`** | `hybrid_rrf` \| `legacy` |
| `AI_RRF_CANDIDATE_K` | `40` | Candidates after RRF before rerank |
| `AI_RRF_K` | `60` | RRF constant |
| `AI_VECTOR_CANDIDATE_K` | `40` | Vector leg fetch size |
| `AI_FTS_CANDIDATE_K` | `40` | FTS leg fetch size |
| `HNSW_EF_SEARCH` | `40` | Runtime `hnsw.ef_search` via `SET LOCAL` in `search_pgvector` |
| `HNSW_M` | `16` | Index build param (migration) |
| `HNSW_EF_CONSTRUCTION` | `64` | Index build param (migration) |

Unchanged: embedding model (`gemini-embedding-001`), dimensions (`1536`), `AI_FINAL_TOP_K`, `AI_MIN_RETRIEVAL_SCORE`.

## Indexes / columns

### Phase 1 — HNSW (`0012_document_chunks_hnsw`)

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_chunks_embedding_hnsw
ON document_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
WHERE embedding IS NOT NULL;
```

- Alembic `autocommit_block()` for `CONCURRENTLY`
- Runtime: `SET LOCAL hnsw.ef_search = <HNSW_EF_SEARCH>` in `PgVectorRetriever.search_pgvector`
- Rollback: `DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_embedding_hnsw`

### Phase 2 — FTS (`0013_document_chunks_fts`)

| Column | Type | Notes |
|--------|------|--------|
| `search_document` | text | `title \|\| ' ' \|\| content` |
| `search_tsv` | tsvector | `to_tsvector('simple', search_document)` via trigger |

- GIN: `ix_document_chunks_search_tsv`
- Trigger: `trg_document_chunks_search_tsv` keeps `search_tsv` in sync
- Ingest populates `search_document` on chunk insert

### Phase 5 — Org override (`0014_ai_config_retrieval_mode`)

| Column | Type | Notes |
|--------|------|--------|
| `ai_configs.retrieval_mode` | varchar(32) NULL | `null` → use env `AI_RETRIEVAL_MODE`; else `legacy` \| `hybrid_rrf` |

Exposed on `GET/PATCH /api/v1/ai/config` as additive field `retrieval_mode`. For single-tenant, leave `null` and control mode via root `.env`.

## Invariants

- Org filter: `KnowledgeSource.organization_id` + `Document.status = COMPLETED`
- Null embeddings excluded from vector path; FTS can still return those chunks
- Do not rewrite migrations `0001`–`0011`
- Knowledge search API (`POST /api/v1/knowledge/search`) remains vector-only

## Rollback

1. Set `AI_RETRIEVAL_MODE=legacy` in root `.env` and recreate backend/worker/beat
2. Or set org `retrieval_mode` to `legacy` (optional)
3. Indexes/columns may remain (harmless) or be dropped via down-migration

## Access patterns

| Mode | Vector | Keyword | Fusion |
|------|--------|---------|--------|
| `hybrid_rrf` (**default**) | pgvector cosine (± HNSW) | FTS | RRF |
| `legacy` (optional) | pgvector cosine (± HNSW) | ILIKE | Weighted merge |

Downstream `Reranker` and `RelevanceGate` stay unchanged.

## Multi-tenant note

HNSW is global on the column; org filtering is in `WHERE`. For large multi-tenant tables, raise `HNSW_EF_SEARCH` and/or overscan with `AI_VECTOR_CANDIDATE_K` if filtered recall drops. Single-tenant deployments typically ignore org `retrieval_mode` and use env only.

## Benchmark harness

```bash
docker compose exec backend python -m scripts.benchmark_retrieval --mode both
```
