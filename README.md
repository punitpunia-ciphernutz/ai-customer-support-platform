Single-tenant **Support Platform Core** (Day 1) plus **Knowledge Base + AI Foundation** (Day 2): auth, RBAC, customers, conversations, messages, tickets, realtime inbox, knowledge ingestion/retrieval (pgvector + Gemini embeddings), LangGraph classification.

## Quick start

See [docs/run-guide.md](docs/run-guide.md).

```bash
cp .env.example .env
docker compose up --build
```

- App: http://localhost:5173  
- API docs: http://localhost:8000/docs  
- Agent login: `agent@example.com` / `agent123!`

## Stack

Backend: FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL + pgvector · Redis · Celery · LangChain · LangGraph · Gemini  
Frontend: React · TypeScript · Vite · TanStack Query · React Hook Form · Zod

## Documentation

- [Codebase map](docs/codebase-map.md) — folders/files and where to change what
- [Day 1 implementation plan](docs/day1-implementation-plan.md)
- [Day 2 implementation plan](docs/day2-implementation-plan.md)
- [Day 1+2 final audit](docs/day1-day2-final-audit.md)
- [Progress](docs/progress.md)
- [Run guide](docs/run-guide.md)
