# Progress — AI Customer Support Platform

Last updated: 2026-08-31

## Status summary

**Day 1, Day 2, and Day 3 are complete.** The platform now runs a full async AI support agent: customer messages trigger Celery → LangGraph → knowledge retrieval → grounded answers or human escalation with tickets.

**Frontend UI (Day 3 follow-up):** Tickets, Teams, and Settings pages are fully wired to backend APIs with loading/empty/error/success states. Settings consolidates all AI configuration (thresholds, intents, team routing, test console, run history).

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

## Frontend — Completed pages

| Page | Backend APIs used | Notes |
|------|-------------------|-------|
| **Inbox** | conversations, messages, customers, users, teams | Assign/close, AI diagnostics panel, WS realtime |
| **Customers** | GET/POST `/customers` | Create + list with loading/error/success states |
| **Knowledge** | knowledge sources, documents, upload, delete | Ingestion status polling |
| **Tickets** | GET/POST/PATCH `/tickets` | List, filter, create, assign, resolve/close; WS ticket events |
| **Teams** | GET/POST `/teams`, GET `/users` | Create teams, list members (no member CRUD API yet) |
| **Settings** | GET/PATCH `/ai/config`, GET `/ai/runs`, POST `/ai/test` | Full AI config, intent routing, test console, run history |
| **Web Chat** | public conversations/messages + WS | Customer-facing demo |

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Verification notes

- **AI mode** defaults to `AUTO_REPLY` (seed). Configure in **Settings → AI Support** or via `PATCH /ai/config`.
- Celery worker must run for async AI replies from Web Chat (`docker compose up worker`).
- Customer public chat hides `metadata.internal` messages (escalation notes).
- Without `GEMINI_API_KEY`: Echo LLM + offline embeddings (sufficient for demos/tests).
- With `GEMINI_API_KEY`: Gemini embeddings + structured LLM output.
- **Tickets page** shows AI-escalated and manually created tickets; filter by status, assign agents/teams, resolve/close.
- **Settings page** is the single place for AI thresholds, allowed/restricted intents, intent→team routing, test console, and run history.
- **Teams page** creates teams and lists org users; team membership API not yet available.
- **Day 3 audit:** [`docs/day3-audit.md`](day3-audit.md) — all 24 requirements complete.
- Audit detail: [`docs/day1-day2-final-audit.md`](day1-day2-final-audit.md)
- Day 3 plan: [`docs/day3-implementation-plan.md`](day3-implementation-plan.md)
