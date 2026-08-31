# Run guide — local development

## Prerequisites

- Docker + Docker Compose
- (Optional) Node 20+ and Python 3.12+ for non-Docker work

## 1. Configure environment

```bash
cd "/path/to/AI Customer Support Platform"
cp .env.example .env
```

Defaults work for local demo. AI settings (**Gemini optional**):

```bash
GEMINI_API_KEY=                 # empty → offline lexical embeddings + Echo/heuristic LLM
LLM_MODEL=gemini-3.1-flash-lite
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=1536
CHUNK_SIZE_TOKENS=600
CHUNK_OVERLAP_TOKENS=80
KNOWLEDGE_TOP_K=5
AI_RETRIEVAL_TOP_K=10
AI_FINAL_TOP_K=5
AI_CONTEXT_MESSAGE_LIMIT=20
AI_MIN_RETRIEVAL_SCORE=0.35
SUPPORT_AGENT_GRAPH_VERSION=support-agent-v1
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
| Frontend (inbox + knowledge + chat) | http://localhost:5173 |
| Backend API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| Agent WebSocket | `ws://localhost:8000/ws?token=<jwt>` |
| Public WebSocket (web chat) | `ws://localhost:8000/ws/public` |
| Postgres (pgvector) | localhost:5432 |
| Redis | localhost:6379 |

On backend start: `alembic upgrade head` (through `0004_day3_ai_agent`) + seed (org, roles, **Billing** team, **AI config**).

**Important:** The **worker** service must be running for async AI replies (`process_ai_message` Celery task).

## 3. Migrate / seed / test

```bash
make migrate
make seed
make test
make logs
make down
```

Full suite (in Docker):

```bash
docker compose exec backend pytest -q
```

Day 3 agent tests (17 tests — all spec scenarios + lifecycle + Celery event path):

```bash
docker compose exec backend pytest -q tests/test_day3_agent.py
```

Targeted Day 1/2 + Day 3:

```bash
docker compose exec backend pytest -q \
  tests/test_semantic_search.py \
  tests/test_celery_ingest.py \
  tests/test_day3_agent.py \
  tests/test_search_and_classify.py
```

> **Note:** With `GEMINI_API_KEY` set in `.env`, `test_gemini_provider` fallback tests expect Gemini providers (not Echo/offline). Unset the key for fully offline test runs.

## 4. Log in

1. Open http://localhost:5173/login  
2. **agent@example.com** / **agent123!**  
3. Inbox loads; sidebar **Knowledge** for KB; **Web Chat** for customer demo  
4. Inbox thread footer: **AI Support** toggle + mode (`Draft Only` / `Suggest` / `Auto Reply`)

## 5. Day 3 demos

### Flow A — AI resolve (password reset)

1. **Knowledge** → add TEXT source → paste **Password Reset Guide**:
   ```
   How do I reset my password? Go to Settings → Security → Reset Password.
   ```
2. Wait for document `COMPLETED` (worker ingests).
3. **Customers** → create customer → copy UUID.
4. **Web Chat** → paste customer ID → ask: *How do I reset my password?*
5. Within a few seconds (Celery): AI Support reply appears via WebSocket.
6. **Inbox** → open conversation → see AI bubble + **AI Information** panel (intent, confidence, knowledge).

Or API quick test (no Celery):

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print(httpx.post(f"{base}/ai/test", headers=h, json={"message": "How do I reset my password?"}).json())
PY
```

### Flow B — Escalation (billing)

1. **Web Chat** as customer → *Can you change my company's billing plan?*
2. AI escalates → ticket created (Billing team when seeded) → internal note in inbox (not visible in Web Chat).
3. Customer sees short handoff message from AI Support.

Verify AI runs:

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print(httpx.get(f"{base}/ai/runs", headers=h).json()[:3])
PY
```

### AI configuration

```bash
# GET config
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/ai/config

# Safe dev mode (no customer auto-replies)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mode":"DRAFT_ONLY"}' http://localhost:8000/api/v1/ai/config
```

## 6. Day 2 demos (still valid)

### Knowledge search

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

### Classification only

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
r = httpx.post(f"{base}/ai/classify", headers={"Authorization": f"Bearer {token}"},
               json={"message": "I cannot log into my account"})
print(r.status_code, r.json())
PY
```

## 7. Day 1 acceptance walkthrough

1. **Customers** → create customer.  
2. **Web Chat** → send message.  
3. **Inbox** → reply, assign, close.  

## 8. Non-Docker (optional)

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

## 9. Troubleshooting

- **No AI reply in Web Chat**: ensure **worker** is running (`docker compose logs worker`); check `ai_configs.enabled` and `mode=AUTO_REPLY`.  
- **Duplicate AI replies**: idempotency via `processing_key` and `metadata.trigger_message_id`; FAILED Celery retries reuse the same `AIRun` row instead of creating duplicates.  
- **Knowledge stays PENDING**: worker not consuming `celery` queue.  
- **403 on `/ai/*`**: run `make seed` to refresh `ai.read` / `ai.write` permissions.  
- **Weak search without API key**: expected with offline lexical embeddings; set `GEMINI_API_KEY` for Gemini.  
- **Agent WS closes**: use `ws://…/ws?token=<jwt>`; web chat uses `/ws/public`.  
- **Internal escalation notes in inbox only**: public chat filters `metadata.internal=true` messages.
