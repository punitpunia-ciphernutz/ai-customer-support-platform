# AI Customer Support Platform

Single-tenant AI customer support: auth/RBAC, inbox, knowledge base (RAG), multi-channel (web chat, email, embeddable widget), AI auto-reply with response policy, automations, SLA, and teams.

## Quick start

See [docs/run-guide.md](docs/run-guide.md).

```bash
cp .env.example .env
docker compose up --build
```

- App: http://localhost:5173  
- API docs: http://localhost:8000/docs  
- Agent login: `agent@example.com` / `agent123!`  
- Full demo users: [docs/progress.md](docs/progress.md)

## Stack

Backend: FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL + pgvector · Redis · Celery · LangChain · LangGraph · Gemini  
Frontend: React · TypeScript · Vite · TanStack Query · React Hook Form · Zod

## Documentation

| Doc | Purpose |
|-----|---------|
| [Run guide](docs/run-guide.md) | Local setup, demos, email/widget/attachment curls |
| [Manual test scenarios](docs/manual-test-scenarios.md) | QA checklist (webchat, email, KB, AI modes) |
| [Codebase map](docs/codebase-map.md) | Where to change what in the repo |
| [Progress](docs/progress.md) | Feature status + demo credentials |
| [Database schemas](docs/database/) | Schema references (widgets, Day 4–6, response policy) |
