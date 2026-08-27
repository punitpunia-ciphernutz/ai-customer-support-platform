# Run guide — local development

## Prerequisites

- Docker + Docker Compose
- (Optional) Node 20+ and Python 3.12+ for non-Docker work

## 1. Configure environment

```bash
cd "/path/to/AI Customer Support Platform"
cp .env.example .env
```

Defaults work for local demo. Day 2 AI settings (**Gemini only** — no OpenAI):

```bash
GEMINI_API_KEY=                 # empty → offline lexical embeddings + heuristic classifier
LLM_MODEL=gemini-3.1-flash-lite
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=1536
CHUNK_SIZE_TOKENS=600
CHUNK_OVERLAP_TOKENS=80
KNOWLEDGE_TOP_K=5
KNOWLEDGE_UPLOAD_DIR=/tmp/support-knowledge
```

Do **not** commit API keys. Change `SECRET_KEY` before any shared deployment.

## 2. Start the stack

```bash
docker compose up --build
# or detached:
make up
```

| Service | URL / port |
|---------|------------|
| Frontend (inbox + knowledge + chat) | http://localhost:5173 (Compose maps host `5173` → container `80`) |
| Backend API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Agent WebSocket | `ws://localhost:8000/ws?token=<jwt>` |
| Public WebSocket (web chat) | `ws://localhost:8000/ws/public` |
| Postgres (pgvector) | localhost:5432 |
| Redis | localhost:6379 |

On backend start: `alembic upgrade head` (through `0003_ai_runs`) + seed (includes `knowledge.*` permissions).

## 3. Migrate / seed / test

```bash
make migrate
make seed
make test
make logs
make down
```

Full suite:

```bash
docker compose exec backend pytest -q
```

Targeted Day 1/2 gap tests:

```bash
docker compose exec backend pytest -q \
  tests/test_semantic_search.py \
  tests/test_celery_ingest.py \
  tests/test_channel_adapter.py \
  tests/test_day1_day2_gaps.py \
  tests/test_gemini_provider.py
```

## 4. Log in

1. Open http://localhost:5173/login  
2. **agent@example.com** / **agent123!**  
3. Inbox loads; use sidebar **Knowledge** for Day 2 UI  
4. Spec alias routes `/app/knowledge` redirect to `/knowledge`

## 5. Day 2 demos

### Flow A — Knowledge

1. UI: **Knowledge** → add a **TEXT** source → open it → paste FAQ text → wait for `COMPLETED`  
   Or API:

```bash
docker compose exec -T backend python - <<'PY'
import httpx, time
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
sid = httpx.post(f"{base}/knowledge/sources", headers=h, json={"name":"FAQ","type":"TEXT"}).json()["id"]
httpx.post(f"{base}/knowledge/sources/{sid}/documents/text", headers=h, json={
  "title": "Password Reset",
  "content": "How do I reset my password? Use Forgot Password on the login page.",
})
for _ in range(20):
    docs = httpx.get(f"{base}/knowledge/sources/{sid}/documents", headers=h).json()
    if docs and docs[0]["status"] in {"COMPLETED", "FAILED"}:
        print(docs[0]["status"]); break
    time.sleep(0.5)
print(httpx.post(f"{base}/knowledge/search", headers=h, json={"query":"How do I reset my password?"}).json())
PY
```

Also supported: PDF upload (`POST .../documents/pdf`) and URL (`POST .../documents/url`) — one URL → one document.

With `GEMINI_API_KEY` set, ingestion/search use **Gemini embeddings** (`gemini-embedding-001`). Without a key, offline lexical embeddings still rank overlapping vocabulary (good enough for local demos).

### Flow B — AI classification

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
r = httpx.post(
    f"{base}/ai/classify",
    headers={"Authorization": f"Bearer {token}"},
    json={"message": "I cannot log into my account"},
)
print(r.status_code, r.json())
PY
```

Expect `intent: ACCOUNT_ACCESS` and an `ai_run_id` (row in `ai_runs`). No auto-reply to customers.

With `GEMINI_API_KEY` set, classification uses **Gemini 3.1 Flash Lite** (`gemini-3.1-flash-lite`) via `LLMProvider` / LangGraph / structured Pydantic output.

## 6. Day 1 acceptance walkthrough

1. **Customers** → create a customer (copy UUID).  
2. **Web Chat** → paste customer ID → send a message.  
3. **Inbox** → reply, assign (user/team), set status/priority, close.  
4. Confirm audit rows for assign/close (DB `audit_logs`).

## 7. Non-Docker (optional)

**Backend:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
# separate terminal:
celery -A app.workers.celery_app worker --loglevel=info
```

**Frontend:**

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## 8. Troubleshooting

- **Knowledge stays PENDING**: ensure worker is running and consuming the `celery` queue (`docker compose logs worker`).  
- **403 on knowledge**: `make seed` to refresh role permissions.  
- **Weak search without API key**: expected with offline lexical embeddings; set `GEMINI_API_KEY` for Gemini embeddings.  
- **Classifier stays heuristic**: set `GEMINI_API_KEY` in `.env` and restart backend/worker.  
- **PDF not found in worker**: backend + worker share `knowledge_uploads` volume at `/tmp/support-knowledge`.  
- **Agent WS closes immediately**: agent inbox needs `ws://…/ws?token=<jwt>`; web chat uses `/ws/public`.  
- **Docker sock errors**: start the daemon, then `docker compose up --build`.
