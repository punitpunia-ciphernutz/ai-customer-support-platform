# Hybrid Search — What Changed

**Date:** 2026-09-09 (default flipped to `hybrid_rrf`)  
**Plan:** [`hybrid-search-implementation-plan.md`](hybrid-search-implementation-plan.md)  
**Validation:** [`hybrid-search-validation.md`](hybrid-search-validation.md)  
**Default behavior:** `AI_RETRIEVAL_MODE=hybrid_rrf` (`legacy` kept as optional rollback)

Implemented Phases 0–5 of the hybrid search plan, then set **hybrid_rrf as the product default**. Single-tenant deployments typically switch via root `.env` only; org override may remain unused (`null`).

---

## Mode comparison: `hybrid_rrf` vs `legacy`

| | **`hybrid_rrf` (default)** | **`legacy` (optional rollback)** |
|--|----------------------------|----------------------------------|
| **Vector** | pgvector cosine (± HNSW) | Same |
| **Keyword** | PostgreSQL **FTS** (`simple` + GIN) | **ILIKE** token match on content/title |
| **Fusion** | **RRF** — `Σ 1/(k + rank)`, `k=60` | Weighted blend (`hybrid_keyword_weight`, default 0.3) |
| **Candidates → reranker** | `AI_RRF_CANDIDATE_K` (40) | `AI_RETRIEVAL_TOP_K` (10) |
| **Best at** | Exact codes/IDs (`AUTH-401`), multi-intent, noisy KB | Stable old behavior / Echo-test expectations |
| **Downstream** | Same Reranker → RelevanceGate → LLM | Same |

### Pipelines

**Default (`hybrid_rrf`):**

```
QueryPreparer → parallel (pgvector±HNSW, FTS) → RRF → Reranker → RelevanceGate → LLM
```

**Rollback (`legacy`):**

```
QueryPreparer → pgvector + ILIKE → weighted merge → Reranker → RelevanceGate → LLM
```

### When to use which

- **Use `hybrid_rrf` (default):** normal production / single-tenant traffic.
- **Use `legacy`:** emergency rollback if retrieval or escalation behavior looks wrong; or to pin older Echo/heuristic tests.

Switch (no code change required for day-to-day):

```bash
# Root .env (Docker Compose loads this) — then recreate backend/worker/beat
AI_RETRIEVAL_MODE=hybrid_rrf   # default
AI_RETRIEVAL_MODE=legacy       # rollback
```

Optional org field `ai_configs.retrieval_mode` still exists (`null` = use env). For single-tenant, leave it `null` and rely on `.env`.

---

## Summary (implementation phases)

| Phase | Deliverable | Notes |
| ----- | ----------- | ----- |
| 0 | Settings + `.env.example` + schema stub | Flags landed |
| 1 | HNSW index + `hnsw.ef_search` | Additive index |
| 2 | FTS columns/GIN/trigger + ingest + `_fts_search` | Used by RRF mode |
| 3 | RRF fusion + `HybridRetriever` modes + graph wiring | Mode switch |
| 4 | Golden tests + benchmark script | Quality gates |
| 5 | Org `retrieval_mode` (optional) | Nullable; unused in single-tenant env-only setup |
| Default flip | `hybrid_rrf` is default; `legacy` optional | settings + `.env` / `.env.example` |

---

## Files created

| File | Purpose |
| ---- | ------- |
| `backend/migrations/versions/0012_document_chunks_hnsw.py` | HNSW cosine index (`CONCURRENTLY`) |
| `backend/migrations/versions/0013_document_chunks_fts.py` | `search_document`, `search_tsv`, GIN, trigger, backfill |
| `backend/migrations/versions/0014_ai_config_retrieval_mode.py` | Nullable `ai_configs.retrieval_mode` |
| `backend/app/modules/ai/infrastructure/retrieval/rrf.py` | Pure RRF fusion |
| `backend/app/modules/ai/infrastructure/retrieval/fts_search.py` | Org-scoped FTS (`simple` config) |
| `backend/scripts/benchmark_retrieval.py` | Latency harness (legacy vs RRF) |
| `backend/scripts/validate_hybrid_search.py` | E2E recall/isolation harness |
| `backend/tests/test_rrf_fusion.py` | RRF unit tests |
| `backend/tests/test_fts_search.py` | FTS / error-code / org isolation |
| `backend/tests/test_hybrid_retriever_modes.py` | Legacy vs `hybrid_rrf` mode isolation |
| `backend/tests/test_hybrid_retrieval_golden.py` | Golden semantic + AUTH-401 queries |
| `docs/database/hybrid-search-schema.md` | Schema/ops reference |

---

## Files modified

| File | Change |
| ---- | ------ |
| `backend/app/config/settings.py` | `ai_retrieval_mode` default **`hybrid_rrf`**, plus RRF/FTS/HNSW knobs |
| `.env` / `.env.example`, `backend/.env.example` | `AI_RETRIEVAL_MODE=hybrid_rrf` |
| `backend/app/modules/knowledge/domain/models.py` | FTS columns on `DocumentChunk`; `AIConfig.retrieval_mode` |
| `backend/app/modules/knowledge/application/ingestion_service.py` | Populates `search_document` on chunk write |
| `backend/app/modules/knowledge/infrastructure/vectorstore/retriever.py` | `SET LOCAL hnsw.ef_search` in `search_pgvector` |
| `backend/app/modules/ai/infrastructure/retrieval/hybrid_retriever.py` | Mode switch; legacy ILIKE merge preserved; RRF path |
| `backend/app/modules/ai/graphs/support_agent.py` | Both retrieve sites use resolved `retrieval_mode` + candidate k |
| `backend/app/modules/ai/application/runtime_config.py` | Resolves org override → env/settings default |
| `backend/app/modules/ai/application/ai_config_service.py` | Validates `retrieval_mode` on PATCH |
| `backend/app/modules/ai/domain/schemas.py` | Additive `retrieval_mode` on AI config DTOs |
| `backend/app/modules/ai/infrastructure/reranker.py` | Heuristic path uses `rrf_rank` when present |
| `docs/database/README.md` | Link to hybrid-search schema doc |

**Unchanged (by design):** `RelevanceGate`, embedding model/dims, knowledge search API contract, historical migrations `0001`–`0011`, ILIKE `_keyword_search` / `_merge_hits`. Reranker LLM path unchanged; heuristic branch only aware of RRF ranks.

---

## How to roll back to legacy

```bash
# Global (env) — recreate backend/worker/beat after change
AI_RETRIEVAL_MODE=legacy

# Optional per-org (usually unused for single-tenant)
PATCH /api/v1/ai/config  {"retrieval_mode": "legacy"}
```

Migrate (indexes/columns):

```bash
make migrate
# or: docker compose exec backend alembic upgrade head
```

---

## Tests / harness

```bash
docker compose exec backend python -m scripts.validate_hybrid_search --repeats 5
docker compose exec backend python -m scripts.benchmark_retrieval --mode both
docker compose exec backend pytest -q \
  tests/test_rrf_fusion.py tests/test_hybrid_retriever_modes.py \
  tests/test_fts_search.py tests/test_hybrid_retrieval_golden.py
```
