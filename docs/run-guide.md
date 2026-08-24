# Run guide — local development

## Prerequisites

- Docker + Docker Compose
- (Optional) Node 20+ and Python 3.12+ for non-Docker work

## 1. Configure environment

```bash
cd "/path/to/AI Customer Support Platform"
cp .env.example .env
```

Defaults are fine for local demo. Change `SECRET_KEY` before any shared deployment.

## 2. Start the stack

```bash
docker compose up --build
# or detached:
make up
```

Services:

| Service | URL / port |
|---------|------------|
| Frontend (inbox + chat) | http://localhost:5173 |
| Backend API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

On backend start, Compose runs `alembic upgrade head` and seeds the demo agent.

## 3. Log in

1. Open http://localhost:5173/login  
2. Use **agent@example.com** / **agent123!**  
3. You land on the **Inbox**

## 4. Acceptance walkthrough

1. Go to **Customers** → create a customer (copy the UUID).  
2. Open **Web Chat** (sidebar link opens `/chat`).  
3. Paste the customer ID → send: `Hello, I need help.`  
4. Return to **Inbox** — conversation appears (realtime via WebSocket).  
5. Open it → reply: `How can I help?`  
6. Assign to yourself, set priority, then **Close**.  
7. Audit rows are written in `audit_logs` for assign/close (inspect via DB or API later).

## 5. Useful commands

```bash
make logs          # follow Compose logs
make migrate       # alembic upgrade head
make seed          # re-run seed
make test          # pytest inside backend container
make down          # stop stack
```

Celery hello-world (inside worker/backend container):

```bash
docker compose exec backend python -c "from app.workers import hello_world; print(hello_world.delay('day1').get(timeout=10))"
```

## 6. Frontend-only / backend-only (without Compose)

**Backend** (needs Postgres + Redis reachable; adjust `.env`):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## 7. Troubleshooting

- **Docker sock errors**: start the Docker daemon, then `docker compose up --build`.  
- **Login fails**: ensure seed ran (`make seed`).  
- **No realtime updates**: confirm Redis is healthy and backend logs show no Redis listener errors.  
- **Web Chat 404 on customer**: create the customer in the agent UI first and use that UUID.
