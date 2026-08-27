# Progress — AI Customer Support Platform

Last updated: 2026-08-27

## Status summary

**Day 1 and Day 2 are complete.** Support Core + Knowledge/AI foundations are in place, including Gemini embeddings, LangChain behind knowledge interfaces, `ConversationService` + ChannelAdapter wiring, inbox/audit/observability fixes, and expanded tests.

LLM: **Google Gemini** (`gemini-3.1-flash-lite`).  
Embeddings: **Gemini** (`gemini-embedding-001`, 1536-d) when `GEMINI_API_KEY` is set; otherwise offline lexical (bag-of-words) embeddings for local demos/tests.

## Day 1 — Completed

| Phase | Work |
|-------|------|
| A–P | Support Core (auth, org, customers, conversations, tickets, WS, Celery hello, AI placeholders, React inbox) |
| Hardening | `ConversationService`; ChannelAdapter on create/message path; inbox status/team assign; audit `ticket.resolved`; request-id logging + FastAPI OTel instrumentation; agent `/ws` requires JWT, public `/ws/public` |

## Day 2 — Completed

| Phase | Work |
|-------|------|
| A | Knowledge module; Source/Document/Chunk; Alembic `0002_knowledge`; RBAC; source CRUD |
| B | TokenChunker (LangChain splitter) + EmbeddingProvider (**Gemini** / offline lexical) |
| C | TEXT / PDF / URL loaders; normalize; content_hash; IngestionService |
| D | Celery `ingest_document`; 202 document APIs; shared upload volume |
| E | PgVectorRetriever via **LangChain** `BaseRetriever` + `POST /api/v1/knowledge/search` |
| F | `LLMProvider` + **Gemini**; AIClassification; AIRun + `0003_ai_runs` |
| G | AIService + LangGraph classification + `POST /api/v1/ai/classify` |
| H | Knowledge UI (`/knowledge`, `/app/knowledge` redirect) |
| I | Tests (semantic multi-doc, Celery ingest, WS/audit/RBAC, ChannelAdapter, no-auto-reply) |

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Verification notes

- Without `GEMINI_API_KEY`: classification uses echo/heuristic; embeddings use offline lexical vectors (token-overlap semantic enough for demos/tests).
- With `GEMINI_API_KEY`: Gemini embeddings + structured classification (`EMBEDDING_MODEL=gemini-embedding-001`, `LLM_MODEL=gemini-3.1-flash-lite`).
- OpenAI is not used for LLM or embeddings.
- Celery must consume the default `celery` queue.
- Audit detail: [`docs/day1-day2-final-audit.md`](day1-day2-final-audit.md)
