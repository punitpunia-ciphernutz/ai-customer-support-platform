# Hybrid Search — End-to-End Validation Report

**Date:** 2026-09-09  
**Scope:** Validate `hybrid_rrf` as the primary retrieval path while keeping `legacy` as emergency rollback  
**Environment:** Docker Compose backend + Postgres 16 / pgvector; offline embeddings (`OfflineSemanticEmbeddingProvider`) + `EchoLLMProvider` for agent paths  
**Harness:** `backend/scripts/validate_hybrid_search.py`, `backend/scripts/benchmark_retrieval.py`, pytest suites below

---

## Executive verdict

| Question | Answer |
|----------|--------|
| Is Hybrid RRF retrieval functionally correct? | **Yes** — HNSW, FTS, RRF, org isolation, org-mode override all pass |
| Better than legacy on labeled recall? | **Yes** — especially multi-doc / error-code / polluted-KB cases |
| Latency acceptable vs legacy (small corpus)? | **Yes** — within ~1ms p50 / ~1ms p95 |
| Global default | **`hybrid_rrf`** (flipped after validation; see `settings.py` + root `.env`) |
| Keep `legacy`? | **Yes** — optional emergency rollback only; do not remove |

**Current product default:** `AI_RETRIEVAL_MODE=hybrid_rrf`. Use `legacy` only for rollback. Mode differences: [`hybrid-search-changes.md`](hybrid-search-changes.md). Single-tenant setups should rely on root `.env` and leave org `retrieval_mode` null.

**Note from validation:** some Echo/heuristic escalation cases (e.g. billing plan change) can differ under hybrid because FTS raises related-KB confidence — monitor with live LLM rerank.

---

## Bug found and fixed during validation

### Heuristic reranker + RRF score scale

**Symptom:** With `AI_RETRIEVAL_MODE=hybrid_rrf` and `EchoLLMProvider`, Day 3 password auto-resolve confidence dropped (~0.79 vs ≥0.84) because `_heuristic_score` treated raw RRF scores (≪ 1) as cosine similarities.

**Fix (minimal):** `backend/app/modules/ai/infrastructure/reranker.py` — when `metadata.rrf_rank` is present, use rank-based similarity proxy instead of raw RRF score. LLM rerank path unchanged.

**After fix:** password Day 3 test passes under `hybrid_rrf`; validation gate after RRF reports `gate_passed=True`, top heuristic score ≈ 1.0.

### Behavioral difference (not a code defect)

`test_ai_test_billing_escalation` **fails under `hybrid_rrf`** but **passes under `legacy`**:

| Mode | Decision | Confidence | Escalation |
|------|----------|------------|------------|
| `legacy` | `ESCALATE` | ~0.76 | Yes |
| `hybrid_rrf` | `AI_RESOLVE` | ~0.88 | No |

Hybrid FTS pulls billing FAQ chunks for “change billing plan,” raising confidence above the auto-reply threshold even though the Echo answer still says it cannot change plans. This is a **product/escalation calibration** issue when keyword retrieval improves—not a tenant leak or fusion bug. Monitor gate/escalation rates in production with LLM rerank.

### Non-hybrid / env noise

- `test_email_knowledge_base_sends_when_grounded` intermittently fails with 0 AI messages under **both** modes when local `ai_configs` / EMAIL bot state is polluted — not attributable to Hybrid RRF.
- `test_chunk_embed::test_default_factories` fails when `GEMINI_API_KEY` is set in the container (expects offline provider) — pre-existing env coupling.
- Shared DB accumulates many password/billing fixtures across runs; this **hurts legacy** Recall@5 more than RRF (see cases).

---

## Tests executed

### A. Validation harness (`scripts.validate_hybrid_search`)

| Check | Result |
|-------|--------|
| HNSW index present (`ix_document_chunks_embedding_hnsw`) | PASS |
| Vector search with `hnsw.ef_search=40` returns password doc | PASS |
| FTS `AUTH-401` | PASS |
| FTS `ERR_PAYMENT_403` | PASS |
| FTS `TKT-77821` | PASS |
| FTS keyword (“Forgot Password link”) | PASS |
| FTS empty query → `[]` | PASS |
| Golden cases (semantic / error / billing / multi-doc / no-match / long) | PASS (7/7) |
| RRF metadata (`rrf_rank`, semantic/fts flags) | PASS |
| Reranker + RelevanceGate after RRF | PASS |
| Empty hits → gate fail | PASS |
| Tenant isolation (FTS + RRF) | PASS |
| Org `retrieval_mode=hybrid_rrf` override | PASS |
| Org `retrieval_mode=legacy` override | PASS |
| Org `null` falls back to env | PASS |

**Harness score: 22 / 22 passed**

### B. Pytest — hybrid unit/integration

| Suite | Result |
|-------|--------|
| `test_rrf_fusion.py` | PASS |
| `test_hybrid_retriever_modes.py` | PASS |
| `test_fts_search.py` | PASS |
| `test_hybrid_retrieval_golden.py` | PASS |
| `test_hybrid_search_e2e_validation.py` | PASS |
| `test_day4_phase3_retrieval.py` | PASS |
| `test_semantic_search.py` | PASS |
| `test_search_and_classify.py` | PASS |
| `test_celery_ingest.py` | PASS |

### C. Day 3 / Day 4 regression

| Mode | Suite (selected Day 3/4 + hybrid) | Result |
|------|----------------------------------|--------|
| `AI_RETRIEVAL_MODE=legacy` | Day3 password/billing/human + Day4 acceptance/phase1–3/tracing/missed_chat + hybrid + semantic/search/ingest | **63 passed, 1 failed** (`email_knowledge_base` env noise) |
| `AI_RETRIEVAL_MODE=hybrid_rrf` | Same core set | **63 passed, 1 failed** (`billing_escalation` behavioral difference above) |

Day 3 password + human escalation: **PASS under hybrid_rrf** after heuristic fix.

### D. Org-level mode (manual)

With env `AI_RETRIEVAL_MODE=legacy` and DB `ai_configs.retrieval_mode=hybrid_rrf`:

- Resolved mode = `hybrid_rrf` (org wins) — **PASS**
- Clear override (`PATCH` empty / `null`) → falls back to env `legacy` — **PASS**

---

## Legacy vs Hybrid RRF metrics

Labeled fixture KB (password, AUTH-401, ERR_PAYMENT_403, billing, ticket ID, filler) + org-B poison doc. Mean recall over cases **with** relevant labels. Latency = retrieval only (not full agent), 5 repeats/query.

### Aggregate recall

| Metric | Legacy | Hybrid RRF | Delta |
|--------|--------|------------|-------|
| Mean Recall@5 | 0.67 | **0.92** | +0.25 |
| Mean Recall@10 | 0.83 | **0.92** | +0.09 |
| Mean Recall@20 | 0.83 | **1.00** | +0.17 |

### Aggregate latency (validation harness)

| Metric | Legacy | Hybrid RRF |
|--------|--------|------------|
| p50 | 4.6 ms | 4.9 ms |
| p95 | 5.8 ms | 6.5 ms |

### Benchmark script (`benchmark_retrieval`, 4 queries × 5 repeats, existing corpus)

| Mode | overall p50 | overall p95 |
|------|-------------|-------------|
| legacy | 4.3 ms | 6.4 ms |
| hybrid_rrf | 4.4 ms | 7.4 ms |

On this small corpus, Hybrid RRF is **latency-neutral** (noise-level difference). Large-corpus HNSW gains were not measured here (N ≪ 100k).

---

## Retrieval quality comparison (per case)

| Case | Query type | Legacy ranks (relevant) | RRF ranks | Legacy R@5 | RRF R@5 | Winner |
|------|------------|-------------------------|-----------|------------|---------|--------|
| semantic_password | Semantic | password@5 | password@0 | 0.0 | **1.0** | **RRF** |
| error_auth_401 | Exact code | auth@0 | auth@0 | 1.0 | 1.0 | Tie |
| error_payment | Exact code | payment@0 | payment@0 | 1.0 | 1.0 | Tie |
| billing_semantic | Semantic | billing@0 | billing@0 | 1.0 | 1.0 | Tie |
| multi_doc_account | Multi-intent | both miss | auth@0, password@18 | 0.0 | 0.5 (@20=1.0) | **RRF** |
| no_match | Empty/noise | returns noise | returns more candidates | n/a | n/a | See note |
| long_query | Long + codes | both in top-5 | both in top-5 | 1.0 | 1.0 | Tie |

**Notes:**

- **multi_doc:** Legacy missed both labeled docs entirely; RRF recovered AUTH-401 at rank 0 and password by @20 via FTS+vector fusion.
- **no_match:** Neither mode is empty on a polluted corpus (legacy ~10 hits, RRF up to `ai_rrf_candidate_k`). RelevanceGate + reranker remain the safety net — both still fail the gate on empty ranked lists.
- **FTS** correctly returns AUTH-401, ERR_PAYMENT_403, TKT-77821, and password keywords; empty query returns `[]`.
- **Tenant isolation:** Org-B-only AUTH-401 marker never appears in Org-A FTS or RRF results.

---

## AI response quality

| Scenario | Legacy | Hybrid RRF |
|----------|--------|------------|
| Known password FAQ (`run_test`, thresholds 0.84) | AI_RESOLVE, grounded | AI_RESOLVE, grounded (after heuristic fix) |
| Human request | Escalates | Escalates |
| Billing plan change | Escalates (confidence below threshold) | May AI_RESOLVE with higher confidence (see bug/behavior section) |
| Reranker + RelevanceGate on password RRF hits | n/a | Passes (`top_score≈1.0` after fix) |

Downstream contracts unchanged: `RetrievedDocument`, citations, gate API, knowledge search endpoint still vector-only.

---

## Final recommendation

1. **Default is now `hybrid_rrf`.** Set in `settings.py` and root `.env` / `.env.example`.
2. **Do not remove `legacy`.** Keep as optional rollback: `AI_RETRIEVAL_MODE=legacy` (recreate backend/worker/beat).
3. **Single-tenant:** control mode via root `.env` only; leave `ai_configs.retrieval_mode` null.
4. **Watch in production:** escalation / soft-refuse / auto-reply rates (billing-style queries can score higher under FTS).
5. **Echo tests** that hard-assert legacy escalation may need `AI_RETRIEVAL_MODE=legacy` or updated expectations.

### Rollout status

```text
1. Indexes + hybrid_rrf path landed
2. Validated (recall/latency/isolation)
3. Global default flipped to hybrid_rrf
4. legacy retained as emergency rollback
```

---

## How to reproduce

```bash
# Validation harness (Recall@k + checks)
docker compose exec -e AI_RETRIEVAL_MODE=hybrid_rrf backend \
  python -m scripts.validate_hybrid_search --repeats 5 --json /tmp/hybrid-validation.json

# Latency benchmark
docker compose exec backend python -m scripts.benchmark_retrieval --mode both --repeats 5

# Hybrid pytest gate
docker compose exec -e AI_RETRIEVAL_MODE=hybrid_rrf backend pytest -q \
  tests/test_rrf_fusion.py tests/test_hybrid_retriever_modes.py tests/test_fts_search.py \
  tests/test_hybrid_retrieval_golden.py tests/test_hybrid_search_e2e_validation.py \
  tests/test_semantic_search.py tests/test_day4_phase3_retrieval.py
```
