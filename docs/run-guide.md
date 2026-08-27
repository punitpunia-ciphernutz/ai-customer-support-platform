# Run guide — local development

## Prerequisites

- Docker + Docker Compose
- (Optional) Node 20+ and Python 3.12+ for non-Docker work

## 1. Configure environment

```bash
cd "/path/to/AI Customer Support Platform"
cp .env.example .env
```

Defaults work for local demo. Optional Day 2 AI settings:

```bash
OPENAI_API_KEY=                 # empty → hash embeddings + heuristic classifier
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
CHUNK_SIZE_TOKENS=600
CHUNK_OVERLAP_TOKENS=80
LLM_MODEL=gpt-4o-mini
KNOWLEDGE_TOP_K=5
KNOWLEDGE_UPLOAD_DIR=/tmp/support-knowledge
```

Change `SECRET_KEY` before any shared deployment.

## 2. Start the stack

```bash
docker compose up --build
# or detached:
make up
```

| Service | URL / port |
|---------|------------|
| Frontend (inbox + knowledge + chat) | http://localhost:5173 |
| Backend API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
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

Targeted Day 2 tests:

```bash
docker compose exec backend pytest -q \
  tests/test_knowledge_models.py \
  tests/test_chunk_embed.py \
  tests/test_ingestion_loaders.py \
  tests/test_search_and_classify.py \
  tests/test_ai_graph.py
```

## 4. Log in

1. Open http://localhost:5173/login  
2. **agent@example.com** / **agent123!**  
3. Inbox loads; use sidebar **Knowledge** for Day 2 UI

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

## 6. Day 1 acceptance walkthrough

1. **Customers** → create a customer (copy UUID).  
2. **Web Chat** → paste customer ID → send a message.  
3. **Inbox** → reply, assign, close.

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
- **Empty/weak search scores without OpenAI**: expected with hash embeddings; set `OPENAI_API_KEY` for semantic retrieval.  
- **PDF not found in worker**: backend + worker share `knowledge_uploads` volume at `/tmp/support-knowledge`.  
- **Docker sock errors**: start the daemon, then `docker compose up --build`.
