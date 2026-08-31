# Progress — AI Customer Support Platform

Last updated: 2026-08-31

## Status summary

**Day 1, Day 2, and Day 3 are complete.** The platform now runs a full async AI support agent: customer messages trigger Celery → LangGraph → knowledge retrieval → grounded answers or human escalation with tickets.

LLM: **Google Gemini** (`gemini-3.1-flash-lite`) when `GEMINI_API_KEY` is set; otherwise **Echo/heuristic** classifier + offline lexical embeddings for local demos/tests.

## Day 1 — Completed

| Phase | Work |
|-------|------|
| A–P | Support Core (auth, org, customers, conversations, tickets, WS, Celery, React inbox) |
| Hardening | `ConversationService`; ChannelAdapter; inbox assign/close; audit; OTel |

## Day 2 — Completed

| Phase | Work |
|-------|------|
| A–I | Knowledge module, ingestion, pgvector search, classification graph, Knowledge UI, tests |

## Day 3 — Completed

| Phase | Work |
|-------|------|
| 1 | Extended `AIRun` + `ai_configs` migration (`0004_day3_ai_agent`); `SupportAgentState`, `AIResponse`, API DTOs |
| 2 | `ContextBuilder` — recent history + customer context |
| 3–7 | LangGraph Support Agent: intent, retrieval, rerank, grounded generation, confidence, decision |
| 8 | Idempotency via `processing_key` + `trigger_message_id`; lifecycle `PENDING` → `RUNNING` → `COMPLETED`/`FAILED`; FAILED retries reuse same run |
| 9 | Celery `process_ai_message` + `message.created` → async enqueue |
| 10–11 | AI replies via WebSocket; escalation → ticket + internal note + customer handoff |
| 12 | APIs: `POST /ai/test`, `GET /ai/runs`, `GET/PATCH /ai/config` |
| 13 | React: AI bubbles (Web Chat + Inbox), agent AI diagnostics panel, AI toggle/mode |
| 14 | `tests/test_day3_agent.py` — **17 tests** (all 6 spec scenarios, lifecycle, idempotency, Celery→WS event) |

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Verification notes

- **AI mode** defaults to `AUTO_REPLY` (seed). Use Inbox AI settings or `PATCH /ai/config` for `DRAFT_ONLY` during safe testing.
- Celery worker must run for async AI replies from Web Chat (`docker compose up worker`).
- Customer public chat hides `metadata.internal` messages (escalation notes).
- Without `GEMINI_API_KEY`: Echo LLM + offline embeddings (sufficient for demos/tests).
- With `GEMINI_API_KEY`: Gemini embeddings + structured LLM output.
- **Day 3 audit:** [`docs/day3-audit.md`](day3-audit.md) — all 24 requirements complete.
- Audit detail: [`docs/day1-day2-final-audit.md`](day1-day2-final-audit.md)
- Day 3 plan: [`docs/day3-implementation-plan.md`](day3-implementation-plan.md)
