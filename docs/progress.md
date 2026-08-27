# Progress — AI Customer Support Platform

Last updated: 2026-08-27

## Status summary

Day 1 **Support Platform Core** is complete. Day 2 **Knowledge Base + AI Foundation** is complete (Flows A + B verified independently).

## Day 1 — Completed

| Phase | Work |
|-------|------|
| A–P | Support Core (auth, org, customers, conversations, tickets, WS, Celery hello, AI placeholders, React inbox) |

## Day 2 — Completed

| Phase | Work |
|-------|------|
| A | Knowledge module; Source/Document/Chunk; Alembic `0002_knowledge`; RBAC; source CRUD |
| B | TokenChunker + EmbeddingProvider (OpenAI / hash fallback) |
| C | TEXT / PDF / URL loaders; normalize; content_hash; IngestionService |
| D | Celery `ingest_document`; 202 document APIs; shared upload volume |
| E | PgVectorRetriever + `POST /api/v1/knowledge/search` |
| F | LLMProvider; AIClassification; AIRun + Alembic `0003_ai_runs` |
| G | AIService + LangGraph classification + `POST /api/v1/ai/classify` |
| H | Knowledge UI (`/knowledge`, `/knowledge/:sourceId`) |
| I | Tests (18 passing) + docs updates |

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Verification notes

- Without `OPENAI_API_KEY`, embeddings use deterministic hash vectors and classification uses keyword heuristics (still end-to-end).
- Set `OPENAI_API_KEY` in `.env` for real embeddings / LLM structured output.
- Celery must consume the default `celery` queue (fixed; do not route Day 2 tasks to a separate unused queue).
