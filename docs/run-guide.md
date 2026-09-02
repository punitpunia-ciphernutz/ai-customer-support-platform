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
GEMINI_API_KEY=                 # empty → offline Echo LLM + lexical embeddings
LLM_MODEL=gemini-3.1-flash-lite
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=1536
AI_RETRIEVAL_TOP_K=10
AI_FINAL_TOP_K=5
AI_CONTEXT_MESSAGE_LIMIT=20
AI_CONTEXT_RECENT_MESSAGE_LIMIT=10
AI_SUMMARY_MESSAGE_THRESHOLD=20
AI_MIN_RETRIEVAL_SCORE=0.35
SUPPORT_AGENT_GRAPH_VERSION=support-agent-v2
```

Do **not** commit API keys. For **offline tests**, leave `GEMINI_API_KEY` empty.

## 2. Start the stack

```bash
docker compose up --build
# or detached:
make up
```

| Service | URL / port |
|---------|------------|
| Frontend | http://localhost:5173 |
| Backend API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

On backend start: `alembic upgrade head` (through **`0005_day4_ai_reliability`**) + seed (prompts, bot configs, evaluation baseline, business hours).

**Important:** The **worker** service must run for async AI replies. The **beat** service runs missed-chat timeout processing every 60 seconds.

## 3. Migrate / seed / test

```bash
make migrate
make seed
make test
```

Day 4 test suite (offline, recommended):

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed
docker compose exec backend pytest -q \
  tests/test_day4_phase1_models.py \
  tests/test_day4_phase2_context.py \
  tests/test_day4_phase3_retrieval.py \
  tests/test_day4_acceptance.py \
  tests/test_day4_modes.py \
  tests/test_day4_missed_chat.py \
  tests/test_day4_takeover.py \
  tests/test_day4_tracing.py
```

Full suite (may hit Gemini quota if key set):

```bash
docker compose exec backend pytest -q
```

Day 3 agent tests (with knowledge ingestion — needs embeddings):

```bash
docker compose exec backend pytest -q tests/test_day3_agent.py
```

## 4. Log in

1. http://localhost:5173/login — **agent@example.com** / **agent123!**
2. **Settings** — AI kill switch, thresholds, require knowledge, multilingual, evaluation runner
3. **Inbox** — takeover, AI suggestions, diagnostics panel
4. **Web Chat** — customer demo (no internal diagnostics)

## 5. Day 4 verification

### Migration check

```bash
docker compose exec backend alembic current
# Should show: 0005_day4_ai_reliability (head)
```

### AI config (extended)

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print(httpx.get(f"{base}/ai/config", headers=h).json())
PY
```

Expect: `min_relevance_score`, `require_knowledge`, `multilingual_enabled`, `mode_display`, `channel_overrides`.

### Evaluation suite (25 cases)

Via UI: **Settings → Run evaluation suite**

Or API:

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print(httpx.post(f"{base}/ai/evaluations/run", headers=h).json())
PY
```

### Takeover

```bash
# Replace CONV_ID
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/conversations/CONV_ID/takeover
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/conversations/CONV_ID/return-to-ai
```

### Agent availability

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/agents/availability
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"is_online": true}' http://localhost:8000/api/v1/agents/availability
```

### Flow A — Autopilot resolve (unchanged from Day 3)

1. Add **Password Reset Guide** in Knowledge → wait `COMPLETED`
2. Web Chat → ask password reset question
3. Worker processes → grounded AI reply
4. Inbox → AI Information panel + run detail with trace/grounding

### Flow B — Escalation with handoff

1. Ask unknown billing question
2. Ticket created with `AI_ESCALATION` source and handoff in description
3. Tickets page shows title + team assignment

### Flow C — Suggest Reply mode

1. Settings → Mode → **Suggest**
2. Customer message → internal AI suggestion in Inbox (not in customer chat)
3. Click **Use Reply** → agent sends message

### Flow D — Kill switch

1. Settings → disable AI Support
2. Customer message → offline notice / waiting (no AI reply)
3. Re-enable AI for normal operation

## 6. Day 3 demos (still valid)

See previous sections for knowledge search, classification, inbox walkthrough.

## 7. Troubleshooting

- **Gemini 429 on tests**: unset `GEMINI_API_KEY` in `.env`, restart backend/worker
- **No AI reply**: worker running, `enabled=true`, `mode=AUTO_REPLY`, not `HUMAN_CONTROL`
- **Duplicate replies**: idempotency via `processing_key`
- **Evaluation fails with embedding errors**: run eval via Echo path (Settings button uses offline graph when no retrieval DB session in eval runner)
- **Schema docs**: [`docs/database/day4-schema.md`](database/day4-schema.md)

## 8. Non-Docker (optional)

```bash
cd backend && alembic upgrade head && python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
celery -A app.workers.celery_app worker --loglevel=info
cd frontend && npm install && npm run dev
```
