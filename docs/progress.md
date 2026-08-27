# Progress — AI Customer Support Platform

Last updated: 2026-08-27

## Status summary

Day 1 **Support Platform Core** is complete. Day 2 **Knowledge Base + AI Foundation** is complete (Flows A + B verified independently). LLM provider is **Google Gemini only** (`gemini-3.1-flash-lite`).

## Day 1 — Completed

| Phase | Work |
|-------|------|
| A–P | Support Core (auth, org, customers, conversations, tickets, WS, Celery hello, AI placeholders, React inbox) |

## Day 2 — Completed

| Phase | Work |
|-------|------|
| A | Knowledge module; Source/Document/Chunk; Alembic `0002_knowledge`; RBAC; source CRUD |
| B | TokenChunker + EmbeddingProvider (hash-local; OpenAI embeddings removed) |
| C | TEXT / PDF / URL loaders; normalize; content_hash; IngestionService |
| D | Celery `ingest_document`; 202 document APIs; shared upload volume |
| E | PgVectorRetriever + `POST /api/v1/knowledge/search` |
| F | `LLMProvider` + **Gemini** (`gemini-3.1-flash-lite`); AIClassification; AIRun + `0003_ai_runs` |
| G | AIService + LangGraph classification + `POST /api/v1/ai/classify` |
| H | Knowledge UI (`/knowledge`, `/knowledge/:sourceId`) |
| I | Tests + docs updates |

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Verification notes

- Without `GEMINI_API_KEY`, classification uses the echo/heuristic fallback; embeddings stay hash-local (end-to-end still works).
- Set `GEMINI_API_KEY` in `.env` later to enable real Gemini structured classification (`LLM_MODEL=gemini-3.1-flash-lite`).
- OpenAI is no longer used for LLM or embeddings.
- Celery must consume the default `celery` queue.
