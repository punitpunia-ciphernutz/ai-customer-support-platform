# Hybrid Search Implementation Plan

**Status:** Implemented Phases 0–5; **default is now `hybrid_rrf`** (`legacy` = optional rollback) — see [`hybrid-search-changes.md`](hybrid-search-changes.md)  
**Source architecture:** `Production-Grade Hybrid Vector Search Architecture`  
**Baseline:** inspected codebase as of 2026-09-08; implementation landed 2026-09-09; default flipped same day  
**Invariant:** PostgreSQL + pgvector, Gemini `gemini-embedding-001` @ 1536 dims, existing LLM/heuristic reranker, existing RelevanceGate, existing APIs/response formats preserved. Legacy retrieval remains available as rollback.

---

## Target flow

```
User Query
  → QueryPreparer (existing)
  → Parallel:
      │  HNSW Vector Search (pgvector)
      │  PostgreSQL FTS
  → RRF Fusion (candidate Top 20–50)
  → Existing Reranker (LLM / heuristic) → Top 5
  → Existing RelevanceGate
  → Existing LLM generation / no-KB policy
```

Legacy path (must remain callable):

```
Query → pgvector exact cosine + ILIKE → weighted merge → Reranker → RelevanceGate → LLM
```

---

## 1. Current retrieval architecture and request flow

### 1.1 Primary path (chat / support agent)

| Step | Location | Behavior |
|------|----------|----------|
| Message ingest | `backend/app/workers/tasks.py` → `AIService.process_customer_message` | Celery / service entry |
| Context | `backend/app/modules/ai/application/context_builder.py` | Sets `organization_id`, history |
| Config | `backend/app/modules/ai/application/runtime_config.py` | Resolves `AIConfig` + channel `BotConfiguration` |
| Graph | `backend/app/modules/ai/graphs/support_agent.py` | LangGraph: intent → policy → language → prepare → retrieve → gate → generate |
| Query prep | `QueryPreparer.prepare` | Appends intent/language hints to user message |
| Hybrid retrieve | `HybridRetriever.search` | Vector + ILIKE + weighted merge |
| Rerank | `Reranker.rank` | Per-hit LLM structured score or heuristic |
| Aggregate | `aggregate_retrieval_score` | `max*0.6 + mean*0.4` |
| Gate | `RelevanceGate.evaluate` | `max(score) >= min_relevance_score` |
| Answer | `generate_answer_node` | LLM + citations; grounding / confidence / decision |

**Exact retrieve node wiring** (`support_agent.py` `retrieve_knowledge_node`):

1. `HybridRetriever(..., keyword_weight=config.hybrid_keyword_weight)`
2. `hybrid.search(..., top_k=settings.ai_retrieval_top_k)` (default **10**)
3. `Reranker(llm=provider).rank(..., top_k=settings.ai_final_top_k)` (default **5**)
4. Map to `RetrievedDocument` with `score=relevance`
5. `RelevanceGate.evaluate(..., threshold=config.min_relevance_score)` → `knowledge_available`

There is a second, near-duplicate retrieval block in the graph fallback path (~lines 451–474) that must stay behavior-compatible when the new pipeline is introduced.

### 1.2 Knowledge search API (separate, vector-only)

`POST /api/v1/knowledge/search` → `PgVectorRetriever.search` only  
**No** hybrid merge, **no** reranker, **no** RelevanceGate.  
File: `backend/app/modules/knowledge/api/routes.py`.

### 1.3 Ingest path (write side)

Ingest → chunk → `embed_documents` → `document_chunks.embedding` (`Vector(1536)`).  
Embeddings: Gemini when `gemini_api_key` set; else `OfflineSemanticEmbeddingProvider` (tests/offline).

### 1.4 Current scoring (not RRF)

| Stage | Mechanism |
|-------|-----------|
| Vector | `ORDER BY embedding.cosine_distance(query)` → `score = max(0, 1 - distance)` |
| Keyword | ILIKE `%token%` on `document_chunks.content` and `documents.title`; token hit ratio |
| Merge | Weighted blend: `sem_weight = 1 - hybrid_keyword_weight` (default 0.3 keyword) |
| Rerank | LLM relevance or `0.55*vector + 0.45*token_overlap` |
| Gate | Max rerank score vs threshold (default 0.35) |

**Absent today:** HNSW/IVFFlat, `tsvector`/GIN FTS, RRF, metadata filters at query time, feature-flagged retrieval modes.

---

## 2. Files / classes / functions involved in vector search

### Embeddings

| Path | Symbols |
|------|---------|
| `backend/app/modules/knowledge/infrastructure/embeddings/provider.py` | `EmbeddingProvider`, `GeminiEmbeddingProvider`, `OfflineSemanticEmbeddingProvider`, `get_embedding_provider`, `EMBEDDING_DIMENSIONS` usage via models |
| `backend/app/modules/knowledge/infrastructure/embeddings/__init__.py` | re-exports |
| `backend/app/modules/knowledge/infrastructure/langchain/adapters.py` | `LangChainEmbeddingAdapter` |
| `backend/app/modules/knowledge/domain/models.py` | `EMBEDDING_DIMENSIONS = 1536` |

### Vector retrieval

| Path | Symbols |
|------|---------|
| `backend/app/modules/knowledge/infrastructure/vectorstore/retriever.py` | `RetrievalHit`, `Retriever`, `PgVectorRetriever.search`, `search_with_metadata`, `search_pgvector` |
| `backend/app/modules/knowledge/infrastructure/langchain/adapters.py` | `LangChainPgVectorRetriever` → calls `search_pgvector` |
| `backend/app/modules/knowledge/infrastructure/vectorstore/__init__.py` | exports |
| `backend/app/modules/knowledge/api/routes.py` | knowledge search endpoint |

### Hybrid / query / rerank / gate

| Path | Symbols |
|------|---------|
| `backend/app/modules/ai/infrastructure/retrieval/hybrid_retriever.py` | `HybridRetriever`, `_keyword_search`, `_merge_hits`, `_tokenize` |
| `backend/app/modules/ai/infrastructure/retrieval/query_preparer.py` | `QueryPreparer.prepare` |
| `backend/app/modules/ai/infrastructure/retrieval/relevance_gate.py` | `RelevanceGate.evaluate` |
| `backend/app/modules/ai/infrastructure/reranker.py` | `Reranker.rank`, `_heuristic_score`, `aggregate_retrieval_score` |
| `backend/app/modules/ai/graphs/support_agent.py` | `retrieve_knowledge_node`, fallback retrieval, `_retriever_for_session` |
| `backend/app/modules/ai/prompts/support_agent_v1.py` | `render_rerank_prompt` |

### Config / tenant scope

| Path | Symbols |
|------|---------|
| `backend/app/config/settings.py` | `embedding_*`, `knowledge_top_k`, `ai_retrieval_top_k`, `ai_final_top_k`, `ai_min_retrieval_score` |
| `backend/app/modules/ai/domain/models.py` | `AIConfig.hybrid_keyword_weight`, `min_relevance_score`, `require_knowledge` |
| `backend/app/modules/ai/application/runtime_config.py` | `RuntimeAIConfig.resolve` (hybrid weight is **org-only**, not channel-overridable) |

### Schema / migrations

| Path | Role |
|------|------|
| `backend/migrations/versions/0002_knowledge.py` | Creates `knowledge_sources`, `documents`, `document_chunks` + `vector` extension |
| `backend/scripts/init-pgvector.sql` | Extension bootstrap |
| `docs/database/day4-schema.md` | AI config / run fields related to retrieval scores |

---

## 3. Current database schema and migrations

### Tables (knowledge)

**`knowledge_sources`:** `id`, `organization_id` (indexed), `name`, `type`, `status`, `configuration`, timestamps.

**`documents`:** `id`, `knowledge_source_id`, `title`, `source_url`, `content`, `content_hash`, `metadata` JSONB, `status`, errors, timestamps. Indexes: source, content_hash, `(source_id, content_hash)`.

**`document_chunks`:** `id`, `document_id`, `content`, `chunk_index`, `token_count`, `metadata` JSONB, **`embedding Vector(1536)`** (nullable), `created_at`. Indexes: `document_id`, `(document_id, chunk_index)`.

### Vector / text indexes today

- **No** HNSW index  
- **No** IVFFlat index  
- **No** GIN/`tsvector` FTS index  
- Similarity is exact `ORDER BY cosine_distance` over org-filtered rows with non-null embeddings

### Latest migration head

`0011_chat_widgets` (revises `0010_response_policy`). Next additive migration should be `0012_*`.

### Multi-tenant query pattern (both vector and keyword today)

```
DocumentChunk → Document → KnowledgeSource
WHERE organization_id = :org
  AND Document.status = COMPLETED
  AND (vector: embedding IS NOT NULL)
```

Metadata on chunks is **stored and returned**, not used as search filters.

---

## 4. Where and how HNSW should be added

### What changes

1. **Alembic migration** (new): create HNSW index on `document_chunks.embedding` using cosine ops, e.g.:

   ```sql
   CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_chunks_embedding_hnsw
   ON document_chunks
   USING hnsw (embedding vector_cosine_ops)
   WITH (m = 16, ef_construction = 64);
   ```

   Exact `m` / `ef_construction` / runtime `ef_search` should be config-tunable and validated in Phase 4 benchmarks.

2. **Optional runtime:** `SET LOCAL hnsw.ef_search = ...` per session/query for recall/latency tradeoff (via settings).

3. **`PgVectorRetriever.search_pgvector`:** keep the same SQL shape (`ORDER BY cosine_distance LIMIT k`). PostgreSQL/pgvector will use the HNSW index when beneficial. No change to embedding model or dimensions.

### Why

Exact cosine scan does not scale as chunk count grows. HNSW provides ANN with high recall while keeping PostgreSQL + pgvector.

### What it affects

- Vector latency/recall on large tables  
- Index build time / disk / write cost on ingest  
- Possibly planner choice for **small** orgs (sequential scan may still win — acceptable)

### How we avoid breaking behavior

- Index is **additive**; queries remain cosine-distance ordered  
- Feature flag not required for index presence (safe when unused)  
- Keep null embeddings excluded (index naturally skips nulls if partial index used — prefer **partial HNSW** `WHERE embedding IS NOT NULL` if pgvector/version supports it; otherwise full index + existing `IS NOT NULL` filter)  
- Regression: existing `test_semantic_search.py`, `test_search_and_classify.py`, `test_celery_ingest.py` must still pass  
- Document that ANN can differ slightly from exact top-k; measure recall@k before enabling as default at scale

### Important multi-tenant caveat

HNSW is typically **global** on the column. Org filtering happens in `WHERE`. For large multi-tenant tables, filtered ANN can under-recall if `ef_search` is too low. Mitigation: raise `ef_search`, fetch larger overscan (`vector_candidate_k > top_k`), and/or later evaluate partial/partitioned strategies. See §13.

---

## 5. How PostgreSQL FTS should be introduced alongside ILIKE

### Current keyword path

`HybridRetriever._keyword_search`:

- Tokenize with `[a-zA-Z0-9]{3,}`, drop `the/and/for/how`, max 6 tokens  
- `ILIKE '%token%'` on chunk content + document title  
- Score = token hit ratio  
- **Problem for support:** hyphens/underscores (e.g. `AUTH-401`, `ERR_PAYMENT_403`) are poorly handled; no ranked FTS; no index → table scans

### What to introduce (alongside, not hard-delete ILIKE)

1. **Generated / maintained search document** on `document_chunks` (preferred) or expression index:

   - Column e.g. `search_tsv tsvector` generated from:
     - `content`
     - joined/denormalized `title` (title must be available — either denormalize title into chunk metadata at ingest, or use a trigger/view; **simplest robust approach:** store `search_document` text = `title || ' ' || content` on chunk at ingest, then `to_tsvector('english', search_document)` or `'simple'` for error codes)
   - For error codes / IDs: prefer **`simple`** dictionary (or dual vectors: `english` + `simple`) so hyphens/underscores/tokens are not stemmed away incorrectly

2. **GIN index** on `search_tsv`

3. **New method** `HybridRetriever._fts_search` (or `FtsRetriever`) using `plainto_tsquery` / `websearch_to_tsquery` + `ts_rank_cd`

4. **Keep `_keyword_search` (ILIKE)** behind the legacy fusion path and optionally as a third leg or fallback when FTS returns empty for alphanumeric codes

### Why

FTS gives indexed keyword ranking and better exact-term retrieval for support content, while ILIKE remains the proven rollback path.

### What it affects

- Ingest must populate/update FTS fields when chunks are written (`IngestionService`)  
- Reindex backfill migration for existing chunks  
- Keyword scores become FTS ranks (different scale than ILIKE hit ratio) — **must not** feed legacy weighted merge without normalization; RRF uses ranks only (preferred)

### How we avoid breaking behavior

- Ship FTS **behind retrieval mode flag** (`legacy` vs `hybrid_rrf`)  
- Legacy mode continues to call `_keyword_search` + `_merge_hits` unchanged  
- Dual-run tests: same fixtures, assert legacy scores unchanged when mode=`legacy`  
- Backfill is additive; no drop of `content` or embeddings

### Recommended FTS query strategy

- Use `websearch_to_tsquery('simple', ...)` for user text when possible  
- For tokens matching error-code patterns (`[A-Z]+[-_][A-Z0-9_-]+`, etc.), also run a phrase/prefix query  
- Preserve org + `COMPLETED` filters identical to vector path

---

## 6. How RRF should be integrated without breaking existing ranking

### Current merge (`_merge_hits`)

Converts heterogeneous scores into a single float via `hybrid_keyword_weight`. Reranker then re-scores. Changing this globally would alter `retrieval_score`, gate pass rates, escalations, and confidence.

### Proposed RRF (new path only)

```
score(d) = Σ 1 / (k_rrf + rank_i(d))
```

- Default `k_rrf = 60` (standard)  
- Inputs: rank lists from vector ANN and FTS (optionally ILIKE as experimental third list — **not** in v1 target)  
- Output: ordered `RetrievalHit` list with:
  - `score` = RRF score (or normalized 0–1 for observability only)
  - `metadata` flags: `semantic`, `fts`, `rrf_rank`, optional per-list ranks  
- Candidate cutoff: **Top 20–50** before rerank (raise effective pool vs today’s `ai_retrieval_top_k=10`)

### Integration point

Prefer **extending `HybridRetriever`** with an explicit strategy rather than rewriting call sites:

```text
HybridRetriever.search(...)
  if mode == "legacy":
      semantic + ILIKE + _merge_hits   # unchanged
  elif mode == "hybrid_rrf":
      semantic (HNSW-backed) + FTS + rrf_fuse
```

`support_agent.py` continues to call `HybridRetriever.search` → `Reranker` → `RelevanceGate` with the same types (`list[RetrievalHit]` → `RetrievedDocument`).

### Why

RRF avoids brittle cross-modal weight tuning and matches the target architecture. Isolating it behind a mode preserves today’s ranking for rollback.

### What it affects

- Candidate set composition into the reranker  
- Indirectly: gate pass rate, confidence, escalations (because different chunks may be reranked)  
- Does **not** change `Reranker` or `RelevanceGate` code in v1

### How we avoid breaking behavior

- Default mode = **`legacy`** until Phase 5 rollout  
- Org/env flag to enable `hybrid_rrf`  
- Keep `hybrid_keyword_weight` meaningful for legacy only; document that it is ignored in RRF mode (or retain as unused for API stability)  
- Shadow mode (optional): run both, log diffs, serve legacy  

---

## 7. Connecting existing reranker and RelevanceGate

### Unchanged contracts

| Component | Contract | Stay the same? |
|-----------|----------|----------------|
| `Reranker.rank(query, hits, top_k)` | `list[RetrievalHit]` → `list[RankedHit]` | Yes |
| `aggregate_retrieval_score` | max/mean blend of relevance | Yes |
| `RelevanceGate.evaluate(docs, threshold, require_knowledge)` | max doc score vs threshold | Yes |
| Graph fields | `retrieved_documents`, `retrieval_score`, `knowledge_available` | Yes |
| Downstream | grounding, confidence, escalation, citations | Yes |

### Pipeline attachment

```
[New or legacy HybridRetriever] → hits (Top K_candidates)
       → Reranker.rank(..., top_k=ai_final_top_k)   # UNCHANGED
       → RetrievedDocument(score=relevance)
       → RelevanceGate.evaluate(...)                 # UNCHANGED
```

### Why keep them unchanged initially

Allows A/B measurement of retrieval quality alone (target doc §9–10). Cross-encoder reranker is explicitly **out of scope** for this upgrade (Phase 6 future).

### Caveats

1. Reranker scores **each hit** with an LLM call when Gemini is available — raising candidates from 10 → 40 increases latency/cost. Mitigations: keep `ai_retrieval_top_k` for legacy; add `ai_rrf_candidate_k` (20–50) only for RRF mode; consider capping LLM rerank to top N later (not v1 unless needed).  
2. Heuristic rerank uses `hit.score`; RRF scores are not cosine similarities. Heuristic path may behave differently offline. Prefer ranking by RRF order when falling back, or map RRF to a bounded score and document the difference for tests using `EchoLLMProvider`.  
3. Fallback graph path currently reranks with `state.user_message` while primary uses `prepared_query` — do not “fix” this in the hybrid project unless intentionally scoped; preserve both call sites’ inputs when wiring the mode flag.

---

## 8. Required configuration / settings changes

### Env / `Settings` (`backend/app/config/settings.py`)

| Key | Proposed default | Purpose |
|-----|------------------|---------|
| `ai_retrieval_mode` | `"legacy"` | `legacy` \| `hybrid_rrf` (global default) |
| `ai_rrf_candidate_k` | `40` | Candidates after RRF before rerank |
| `ai_rrf_k` | `60` | RRF constant |
| `ai_vector_candidate_k` | `40` | Per-list vector fetch size (may overscan for filters) |
| `ai_fts_candidate_k` | `40` | Per-list FTS fetch size |
| `hnsw_ef_search` | `40` (tune) | Runtime HNSW search width |
| `hnsw_m` / `hnsw_ef_construction` | `16` / `64` | Documented for migration; not necessarily runtime |

**Do not change defaults of:** `embedding_model`, `embedding_dimensions` (1536), `ai_final_top_k` (5), `ai_min_retrieval_score` (0.35), `knowledge_top_k` (5) for the public search API unless explicitly productized later.

### Org `AIConfig` (optional Phase 5)

| Column | Purpose |
|--------|---------|
| `retrieval_mode` | Per-org override: `null` = use settings default |
| Keep `hybrid_keyword_weight` | Legacy merge only |

Expose on `GET/PATCH /api/v1/ai/config` only when ready; until then **env-only flag** avoids API contract churn.

### `.env.example`

Document new keys; do not require them for current deploys (defaults = legacy).

### RuntimeAIConfig

When org override exists, resolve `retrieval_mode` like other AI fields. Channel override is optional and not required for v1.

---

## 9. Required database indexes and migrations

### Migration A — HNSW (Phase 1)

- Revision: `0012_document_chunks_hnsw` (name illustrative)  
- `down_revision = "0011_chat_widgets"`  
- Create HNSW index on `document_chunks.embedding` with `vector_cosine_ops`  
- Prefer non-blocking create in production (`CONCURRENTLY` — note Alembic often needs `isolation_level` / run outside a transaction)  
- Downgrade: `DROP INDEX`

**Docs:** add `docs/database/hybrid-search-schema.md` and link from `docs/database/README.md`.

### Migration B — FTS (Phase 2)

- Revision: `0013_document_chunks_fts`  
- Add `search_document` (text) and/or `search_tsv` (`tsvector`) on `document_chunks`  
- Backfill from `content` + document `title` (SQL join update)  
- GIN index on `search_tsv`  
- Optional trigger / generated column to keep FTS in sync on content updates  
- Ingest path update in same phase (application code)  
- Downgrade: drop index + columns

### No destructive changes

- Do **not** alter `embedding` dimensions  
- Do **not** rewrite historical migrations `0001`–`0011`  
- Do **not** remove ILIKE code paths

---

## 10. Required tests and regression tests

### Unit tests (new)

| Area | Suggested file | Cases |
|------|----------------|-------|
| RRF fusion | `backend/tests/test_rrf_fusion.py` | Overlap, disjoint lists, stable ties, `k_rrf` effect |
| FTS query builder | `backend/tests/test_fts_search.py` | Empty query, error codes, org isolation, ranking |
| Mode switch | `backend/tests/test_hybrid_retriever_modes.py` | `legacy` ≡ current merge; `hybrid_rrf` uses RRF |

### Regression (must stay green)

| Existing file | Why |
|---------------|-----|
| `test_day4_phase3_retrieval.py` | QueryPreparer + RelevanceGate |
| `test_semantic_search.py` | Cosine ranking |
| `test_search_and_classify.py` | Retriever + classify |
| `test_chunk_embed.py` | Chunk/embed dimensions |
| `test_celery_ingest.py` | Ingest → searchable chunks |
| `test_day3_agent.py` | Reranker + end-to-end agent |
| `test_day5_email_knowledge_base.py` | Email + KB path |

### Integration / golden set (Phase 4)

- Fixture KB with: password-reset semantic doc, `AUTH-401` exact doc, unrelated filler  
- Queries from the architecture doc examples  
- Assert: RRF mode ranks exact-code doc ≥ semantic-only baseline for code queries; semantic query still retrieves password-reset  
- Gate + citation shapes unchanged for `POST /api/v1/ai/test`

### Explicit non-goals for v1 tests

- Do not require live Gemini for CI (offline embeddings + heuristic rerank)  
- Do not change knowledge search API response schema tests unless API hybrid is separately approved

---

## 11. Performance / recall benchmarking strategy

### Metrics

| Metric | Definition |
|--------|------------|
| Latency p50/p95 | Vector-only, FTS-only, full retrieve node, end-to-end agent |
| Recall@k | Fraction of labeled relevant chunk IDs in top-k (k ∈ {5,10,20,40}) |
| nDCG@k / MRR | If graded relevance labels available |
| Gate pass rate | % conversations with `knowledge_available=true` |
| Escalation / soft-refuse rate | Should not spike without label support |
| Rerank cost | LLM calls ≈ candidate count |

### Methodology

1. Build a labeled eval set (fixtures / golden queries) with semantic, keyword/code, and distractor cases.  
2. Run **shadow comparisons**: same query → legacy vs hybrid_rrf; log rank diffs without serving RRF.  
3. Scale tests: synthetic N ∈ {1k, 10k, 100k+} chunks; measure exact vs HNSW latency and recall vs exact ground truth.  
4. Tune `ef_search`, `ai_vector_candidate_k`, `ai_rrf_candidate_k` before production default flip.  
5. Multi-tenant soak: many orgs, skewed chunk counts — verify org isolation and filtered recall.

### Success criteria (suggested)

- Latency at 100k chunks: hybrid retrieve p95 materially better than exact scan baseline  
- Recall@20 ≥ exact cosine recall@20 within agreed tolerance (e.g. ≥ 95% of exact)  
- Error-code queries: relevant doc in top-5 after rerank ≥ baseline ILIKE hybrid  
- No increase in cross-tenant leakage (hard fail)  
- With mode=`legacy`, bit-identical merge behavior on unit fixtures

---

## 12. Backward compatibility and rollback strategy

### Compatibility matrix

| Surface | Compatibility rule |
|---------|-------------------|
| `POST /api/v1/knowledge/search` | Unchanged (vector-only) unless separately flagged later |
| `POST /api/v1/ai/test` / chat AI responses | Same DTO shapes |
| `AIConfig` API | No required new fields until Phase 5; additive only |
| Embeddings | Same model + 1536 dims; no re-embed required for HNSW |
| Reranker / RelevanceGate | Code unchanged in Phases 1–5 |
| Legacy hybrid | Remain default until explicit enable |

### Rollback levers (fast → slow)

1. **Config:** set `ai_retrieval_mode=legacy` (instant)  
2. **Org override:** force legacy per tenant  
3. **Code:** feature still present; no deploy required if env rollback works  
4. **Index:** HNSW/GIN can remain (harmless) or be dropped via down-migration if operationally needed  
5. **Never** delete ILIKE/`_merge_hits` in the first production release cycle

### Shadow / canary

1. Deploy code + indexes with default `legacy`  
2. Enable `hybrid_rrf` for internal org / staging  
3. Canary % of production orgs  
4. Full default flip only after Phase 4 gates pass  

---

## 13. Risks and edge cases

### Multi-tenant / metadata

| Risk | Detail | Mitigation |
|------|--------|------------|
| Cross-org leakage | Bug in FTS/RRF SQL omitting `organization_id` | Shared query helper enforcing org + COMPLETED; isolation tests |
| Filtered HNSW under-recall | Global index + selective org filter | Overscan (`vector_candidate_k`), higher `ef_search`, monitor recall per org size |
| Metadata filters | Stored but unused today; future filters must apply to **both** vector and FTS before RRF | Design FTS/vector helpers with optional filter kwargs now (unused) |
| Incomplete docs | Only `COMPLETED` documents | Keep identical filter |
| Chunks without embeddings | Vector skips; FTS can still return | RRF may surface keyword-only chunks — desirable for error codes |

### Query / language

| Risk | Detail | Mitigation |
|------|--------|------------|
| Error codes / IDs | Current ILIKE tokenizer drops short/odd tokens | `simple` FTS + pattern-aware query prep |
| `QueryPreparer` intent hints | Extra tokens can dilute FTS | Consider FTS on raw `user_message` + vector on prepared query (evaluate in Phase 3); document choice |
| Non-English | `language:` hint + english FTS config | Prefer `simple` or language-aware config later; don’t break multilingual flag |
| Empty tokens | Both legs empty | Return `[]`; gate behaves as today |

### Operational

| Risk | Detail | Mitigation |
|------|--------|------------|
| Index build lock | HNSW create on large table | `CONCURRENTLY`, maintenance window |
| Ingest lag | FTS column not updated | Same transaction as chunk insert; backfill job |
| Rerank cost explosion | More candidates | Cap `ai_rrf_candidate_k`; monitor |
| Heuristic rerank + RRF scores | Offline tests skew | Unit-test RRF separately; agent tests pin mode=`legacy` unless testing RRF |
| Planner ignores HNSW on tiny data | Expected | Benchmarks on realistic sizes |

### Product / ranking

| Risk | Detail | Mitigation |
|------|--------|------------|
| Gate pass rate shift | Better retrieval may raise or lower scores after LLM rerank | Shadow metrics before default flip |
| Duplicate near-identical chunks | RRF may promote duplicates | Optional document-level diversity later (out of scope) |

---

## 14. Exact files to create / modify / delete

### Create

| File | Purpose |
|------|---------|
| `backend/migrations/versions/0012_document_chunks_hnsw.py` | HNSW index |
| `backend/migrations/versions/0013_document_chunks_fts.py` | FTS columns + GIN + backfill |
| `backend/app/modules/ai/infrastructure/retrieval/rrf.py` | Pure RRF fusion helper |
| `backend/app/modules/ai/infrastructure/retrieval/fts_search.py` | FTS query helpers (optional split from hybrid) |
| `docs/database/hybrid-search-schema.md` | Schema/ops reference |
| `backend/tests/test_rrf_fusion.py` | RRF unit tests |
| `backend/tests/test_fts_search.py` | FTS unit/integration |
| `backend/tests/test_hybrid_retriever_modes.py` | Legacy vs RRF mode |
| `backend/scripts/benchmark_retrieval.py` (optional) | Latency/recall harness |

### Modify

| File | Change |
|------|--------|
| `backend/app/modules/knowledge/domain/models.py` | Optional ORM fields for `search_tsv` / `search_document` |
| `backend/app/modules/knowledge/application/ingestion_service.py` | Populate FTS fields on chunk write |
| `backend/app/modules/knowledge/infrastructure/vectorstore/retriever.py` | Optional `ef_search` session setting; candidate overscan param (backward-compatible defaults) |
| `backend/app/modules/ai/infrastructure/retrieval/hybrid_retriever.py` | Mode switch; FTS leg; RRF path; **keep** ILIKE + `_merge_hits` |
| `backend/app/modules/ai/graphs/support_agent.py` | Pass retrieval mode / candidate k from settings or config (minimal wiring) |
| `backend/app/config/settings.py` | New settings keys (defaults preserve legacy) |
| `.env.example` | Document new keys |
| `backend/app/modules/ai/domain/models.py` / `schemas.py` / `runtime_config.py` / `ai_config_service.py` | Optional Phase 5 org `retrieval_mode` |
| `docs/database/README.md` | Link hybrid-search schema doc |

### Do **not** modify (initially)

| File | Reason |
|------|--------|
| `backend/app/modules/ai/infrastructure/reranker.py` | Keep unchanged |
| `backend/app/modules/ai/infrastructure/retrieval/relevance_gate.py` | Keep unchanged |
| Embedding provider / dimensions | Keep Gemini 1536 |
| Knowledge search response schemas | API contract freeze |
| Historical migrations `0001`–`0011` | Never rewrite |

### Delete

**Nothing** in Phases 1–5. ILIKE and weighted merge remain. Future cleanup of dead code only after hybrid_rrf is default and legacy is retired by explicit decision.

---

## 15. Recommended implementation order (small, safe phases)

Aligned with the architecture doc, adapted to this codebase.

### Phase 0 — Prep (docs/flags only)

- Land this plan  
- Add settings stubs with defaults (`ai_retrieval_mode=legacy`) **without** changing retrieval behavior  
- Add empty/module skeletons only if needed for imports — prefer delaying code until Phase 1–3 tasks

### Phase 1 — HNSW

- Migration `0012` HNSW index  
- Optional `hnsw.ef_search` setting applied in `search_pgvector`  
- Validate existing semantic tests  
- Schema doc update  
- **No** fusion changes

### Phase 2 — FTS alongside ILIKE

- Migration `0013` + backfill  
- Ingest writes FTS fields  
- Implement `_fts_search` but **do not** switch default merge yet  
- Unit tests for FTS isolation and ranking  
- Legacy path still ILIKE

### Phase 3 — RRF path (flagged off)

- Implement `rrf.py` + `HybridRetriever` mode `hybrid_rrf`  
- Wire settings `ai_rrf_*`  
- Graph uses mode from settings (default legacy)  
- Tests for mode isolation  
- Reranker + RelevanceGate untouched

### Phase 4 — Validation / benchmarking

- Golden queries + latency/recall harness  
- Shadow logging (optional)  
- Tune `ef_search` and candidate sizes  
- Confirm API/agent regressions green

### Phase 5 — Production rollout

- Enable per-org or env canary  
- Monitor gate/escalation/latency  
- Keep legacy rollback  
- Optional: expose `retrieval_mode` on AI config API (additive)

### Phase 6 — Future (out of scope now)

- Cross-encoder reranker evaluation  
- Metadata filters  
- Knowledge search API hybrid parity  
- Retire legacy ILIKE merge if metrics allow

---

## Per-change impact summary

| Change | What | Why | Affects | Non-break guarantee |
|--------|------|-----|---------|---------------------|
| HNSW index | DB index on embeddings | Scale ANN | Query plans, ingest write amp | Additive; same SQL; default behavior preserved |
| `ef_search` setting | Session tune | Recall/latency | Vector results at scale | Default matches pgvector defaults until tuned |
| FTS columns + GIN | Indexed keyword | Exact terms / codes | Storage, ingest | Unused until mode on; backfill additive |
| FTS search method | New keyword leg | Ranked keyword | Only RRF mode | Legacy still ILIKE |
| RRF fusion | Rank fusion | Replace brittle weights | Candidate order into reranker | Behind `hybrid_rrf`; legacy `_merge_hits` intact |
| Settings flags | Mode + ks | Safe rollout | Config surface | Defaults = current behavior |
| Org `retrieval_mode` | Per-tenant switch | Canary/rollback | AI config API (additive) | Nullable = global default |
| Graph wiring | Read mode | Route pipeline | `retrieve_knowledge_node` + fallback | Same outputs/types |
| Ingest FTS populate | Write path | Keep index fresh | IngestionService | Embeddings path unchanged |
| Tests/benchmarks | Quality gates | Prove gains | CI time | Pin legacy in existing e2e unless marked |

---

## Implementation Checklist

Sequential tasks suitable for handing to Cursor **one phase at a time**. Do not skip phase gates.

### Phase 0 — Planning / safety rails

- [ ] Confirm this plan reviewed against staging DB pgvector version (HNSW supported).  
- [ ] Add `ai_retrieval_mode` (default `legacy`) and related settings **without** branching retrieval yet (or with dead code paths unused).  
- [ ] Update `.env.example` comments.  
- [ ] Create `docs/database/hybrid-search-schema.md` stub and link from `docs/database/README.md`.

### Phase 1 — HNSW

- [ ] Write Alembic `0012_*` creating HNSW (`vector_cosine_ops`) on `document_chunks.embedding`.  
- [ ] Handle `CONCURRENTLY` / non-transactional index create for production safety.  
- [ ] Add downgrade `DROP INDEX`.  
- [ ] Optionally apply `hnsw.ef_search` in `PgVectorRetriever.search_pgvector`.  
- [ ] Run targeted tests: `test_semantic_search`, `test_search_and_classify`, `test_celery_ingest`.  
- [ ] Document index params and rollback in `hybrid-search-schema.md`.  
- [ ] **Gate:** staging query plans show index usage on large synthetic data; small-data sequential scan acceptable.

### Phase 2 — FTS (parallel to ILIKE)

- [ ] Design FTS representation (`simple` vs `english`; title+content).  
- [ ] Alembic `0013_*`: columns, GIN, backfill SQL from chunks ⋈ documents.  
- [ ] Update `DocumentChunk` model.  
- [ ] Update `IngestionService` to populate FTS fields on insert.  
- [ ] Implement FTS search helper with **same org + COMPLETED filters**.  
- [ ] Unit/integration tests: org isolation, `AUTH-401`-style terms, empty query.  
- [ ] **Do not** change default `HybridRetriever` merge yet.  
- [ ] **Gate:** backfill complete; FTS queries return expected chunks in isolation tests.

### Phase 3 — RRF (flagged)

- [ ] Implement pure `rrf_fuse(ranked_lists, k=60) → list[RetrievalHit]`.  
- [ ] Extend `HybridRetriever` with `legacy` vs `hybrid_rrf` modes.  
- [ ] RRF mode: vector (`ai_vector_candidate_k`) + FTS (`ai_fts_candidate_k`) → RRF → `ai_rrf_candidate_k`.  
- [ ] Preserve `_keyword_search` + `_merge_hits` for `legacy`.  
- [ ] Wire mode from `settings.ai_retrieval_mode` in `support_agent.py` (both retrieve sites).  
- [ ] Leave `Reranker` and `RelevanceGate` untouched.  
- [ ] Tests: legacy fixtures unchanged; RRF unit tests; mode switch test.  
- [ ] **Gate:** default mode still matches pre-change hybrid behavior on golden fixtures.

### Phase 4 — Validation

- [ ] Build labeled query set (semantic, error-code, distractor).  
- [ ] Benchmark latency + recall (exact vs HNSW; legacy vs RRF).  
- [ ] Optional shadow logging of rank diffs.  
- [ ] Tune `ef_search` and candidate sizes; record chosen values.  
- [ ] Full regression of agent/email KB tests with mode=`legacy` and a dedicated RRF suite.  
- [ ] **Gate:** metrics meet §11 success criteria; no tenant leakage.

### Phase 5 — Rollout

- [ ] Enable `hybrid_rrf` in staging for all traffic.  
- [ ] Canary one production org / low % traffic.  
- [ ] Monitor retrieval latency, gate pass rate, escalations, error rates.  
- [ ] Optional additive `AIConfig.retrieval_mode` + API schema fields.  
- [ ] Document rollback: set mode to `legacy`.  
- [ ] **Gate:** stable canary → broaden; keep legacy code path.

### Phase 6 — Future (separate project)

- [ ] Evaluate cross-encoder reranker vs current LLM/heuristic.  
- [ ] Metadata / source filters on both legs.  
- [ ] Decide fate of ILIKE legacy path.  
- [ ] Optional hybrid knowledge search API (contract change — product approval required).

---

## Appendix A — Current vs proposed component matrix

| Component | Current (codebase) | Proposed |
|-----------|-------------------|----------|
| DB | PostgreSQL | Same |
| Vectors | pgvector `Vector(1536)` | Same |
| Embeddings | Gemini `gemini-embedding-001` | Same |
| Vector index | None (exact) | HNSW cosine |
| Keyword | ILIKE | FTS (+ ILIKE legacy) |
| Fusion | Weighted merge | RRF (new path) |
| Candidates into rerank | `ai_retrieval_top_k` (10) | RRF Top 20–50 |
| Reranker | LLM / heuristic | Same initially |
| RelevanceGate | Threshold on max score | Same initially |
| Final context | Top 5 | Same |
| APIs | Unchanged contracts | Unchanged |
| Rollback | N/A | `ai_retrieval_mode=legacy` |

## Appendix B — Key code anchors

```
retrieve_knowledge_node  → backend/app/modules/ai/graphs/support_agent.py
HybridRetriever          → backend/app/modules/ai/infrastructure/retrieval/hybrid_retriever.py
search_pgvector          → backend/app/modules/knowledge/infrastructure/vectorstore/retriever.py
Reranker                 → backend/app/modules/ai/infrastructure/reranker.py
RelevanceGate            → backend/app/modules/ai/infrastructure/retrieval/relevance_gate.py
DocumentChunk.embedding  → backend/app/modules/knowledge/domain/models.py
Migration head           → backend/migrations/versions/0011_chat_widgets.py
```
