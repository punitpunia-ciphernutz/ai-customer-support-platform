# AI Customer Support Platform

Single-tenant **Support Platform Core** (Day 1): auth, RBAC, customers, conversations, messages, tickets, realtime inbox, AI placeholders.

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

Backend: FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL + pgvector · Redis · Celery  
Frontend: React · TypeScript · Vite · TanStack Query · React Hook Form · Zod

## Documentation

- [Day 1 implementation plan](docs/day1-implementation-plan.md)
- [Progress](docs/progress.md)
- [Run guide](docs/run-guide.md)
# ai-customer-support-platform
