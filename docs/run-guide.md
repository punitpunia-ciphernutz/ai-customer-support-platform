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
| Frontend (inbox, tickets, teams, settings, knowledge, chat) | http://localhost:5173 |
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
3. Inbox loads; sidebar **Knowledge** for KB; **Tickets** for escalations; **Teams** for routing; **Settings** for AI config  
4. **Web Chat** (new tab) for customer demo  
5. Inbox thread footer links to **Settings →** for AI configuration

## 5. Frontend pages walkthrough

### Tickets

1. Open **Tickets** in the sidebar.  
2. Filter by status (Open, In Progress, Waiting, Resolved, Closed).  
3. Select a ticket to view details, assign agent/team, change priority, resolve, or close.  
4. Click **+ New ticket** to create manually — select a conversation, optional priority and assignee.  
5. AI escalations from Web Chat appear automatically (requires worker running).

### Teams

1. Open **Teams** — seed data includes a **Billing** team.  
2. Create new teams with name (required) and optional description.  
3. View organization members available for assignment.  
4. Team membership management is not yet available via API.

### Settings (AI configuration)

1. Open **Settings** — all AI configuration lives here.  
2. Toggle AI enabled, set mode (Draft Only / Suggest / Auto Reply).  
3. Adjust auto-reply and escalation thresholds (0–1 sliders).  
4. Configure allowed/restricted intents and intent→team routing.  
5. Use **AI test console** for synchronous debugging (no Celery).  
6. Review **Recent AI runs** — click a run for full input/output details.

## 6. Day 3 demos

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
4. **Tickets** page shows the new ticket — assign, update status, or resolve.

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

Configure via **Settings** page in the UI, or via API:

```bash
# GET config
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/ai/config

# Safe dev mode (no customer auto-replies)
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"mode":"DRAFT_ONLY"}' http://localhost:8000/api/v1/ai/config
```

## 7. Day 2 demos (still valid)

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

## 8. Day 1 acceptance walkthrough

1. **Customers** → create customer.  
2. **Web Chat** → send message.  
3. **Inbox** → reply, assign, close.  

## 9. Non-Docker (optional)

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

## 10. Troubleshooting

- **No AI reply in Web Chat**: ensure **worker** is running (`docker compose logs worker`); check `ai_configs.enabled` and `mode=AUTO_REPLY`. If worker logs show `Future attached to a different loop`, restart the worker after pulling the Celery `run_async` fix. Gemini **429 RESOURCE_EXHAUSTED** also blocks replies until quota resets (or unset `GEMINI_API_KEY` for offline Echo).  
- **Duplicate AI replies**: idempotency via `processing_key` and `metadata.trigger_message_id`; FAILED Celery retries reuse the same `AIRun` row instead of creating duplicates.  
- **Knowledge stays PENDING**: worker not consuming `celery` queue — click **Retry** (↻) on the source or document row to re-queue ingestion once the worker is running.
- **403 on Settings / AI**: run `make seed` to refresh `ai.read` / `ai.write` permissions. Agent role has AI access; READ_ONLY can view but not edit.  
- **Weak search without API key**: expected with offline lexical embeddings; set `GEMINI_API_KEY` for Gemini.  
- **Agent WS closes**: use `ws://…/ws?token=<jwt>`; web chat uses `/ws/public`.  
- **Internal escalation notes in inbox only**: public chat filters `metadata.internal=true` messages.
