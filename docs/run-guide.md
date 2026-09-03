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

# Day 5 — email + attachments (mock provider works offline)
EMAIL_PROVIDER=mock
EMAIL_FROM_ADDRESS=support@acme.example
RESEND_API_KEY=
STORAGE_ROOT_DIR=/tmp/support-attachments
EMAIL_WEBHOOK_SECRET=mock-secret
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

On backend start: `alembic upgrade head` (through **`0008_day6_automation`**) + seed (prompts, bot configs, channel configs, evaluation baseline, business hours, default automations, SLA policies).

**Important:** The **worker** service must run for async AI replies. The **beat** service runs missed-chat timeout processing every 60 seconds and **SLA breach checks** every 60 seconds.

## 3. Migrate / seed / test

```bash
make migrate
make seed
make test
```

Day 5 test suite (email + omnichannel):

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed
docker compose exec backend pytest -q \
  tests/test_day5_phase1_models.py \
  tests/test_day5_customer_resolver.py \
  tests/test_day5_email_inbound.py \
  tests/test_day5_email_outbound.py \
  tests/test_day5_email_threading.py \
  tests/test_day5_email_ai_suggest.py \
  tests/test_day5_email_autopilot.py \
  tests/test_day5_email_escalation.py \
  tests/test_day5_attachments.py \
  tests/test_day5_bot_config_patch.py \
  tests/test_day5_attachments_inbound.py \
  tests/test_day5_attachments_outbound.py \
  tests/test_day5_email_suggest_accept_send.py \
  tests/test_day5_email_knowledge_base.py \
  tests/test_day5_webhook_enabled.py \
  tests/test_channel_adapter.py
```

Expected: **23/23 passed**

Day 6 test suite (automation + routing — full):

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed
docker compose exec backend pytest -q \
  tests/test_day6_phase1_models.py \
  tests/test_day6_conditions.py \
  tests/test_day6_business_hours.py \
  tests/test_day6_assignment_round_robin.py \
  tests/test_day6_acceptance.py \
  tests/test_day6_actions.py \
  tests/test_day6_execution_logs.py \
  tests/test_day6_loop_protection.py \
  tests/test_day6_idempotency.py \
  tests/test_day6_availability.py \
  tests/test_day6_missed_chat_delayed.py \
  tests/test_day6_sla_timers.py \
  tests/test_day6_notifications.py \
  tests/test_day6_event_integration.py \
  tests/test_day6_automation_api.py
```

Expected: **25/25 passed**

Day 6 + Day 4/5 regression subset:

```bash
docker compose exec backend pytest -q \
  tests/test_day6_phase1_models.py \
  tests/test_day6_conditions.py \
  tests/test_day6_business_hours.py \
  tests/test_day6_assignment_round_robin.py \
  tests/test_day6_acceptance.py \
  tests/test_day6_actions.py \
  tests/test_day6_execution_logs.py \
  tests/test_day6_loop_protection.py \
  tests/test_day6_idempotency.py \
  tests/test_day6_availability.py \
  tests/test_day6_missed_chat_delayed.py \
  tests/test_day6_sla_timers.py \
  tests/test_day6_notifications.py \
  tests/test_day6_event_integration.py \
  tests/test_day6_automation_api.py \
  tests/test_day4_missed_chat.py \
  tests/test_day4_takeover.py \
  tests/test_day5_webhook_enabled.py \
  tests/test_day5_phase1_models.py
```

Expected: **33/33 passed**

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

Expected: **97/101** — 4 failures are pre-existing when `GEMINI_API_KEY` is set (`test_chunk_embed`, `test_gemini_provider` ×2, `test_semantic_search`). For offline CI, leave `GEMINI_API_KEY` empty.

Day 3 agent tests (with knowledge ingestion — needs embeddings):

```bash
docker compose exec backend pytest -q tests/test_day3_agent.py
```

## 4. Log in

1. http://localhost:5173/login — use any demo account below (password **`agent123!`**)
2. **Settings** — AI kill switch, model selection, thresholds, require knowledge, multilingual, evaluation runner
3. **Inbox** (`/` or `/app/inbox`) — takeover, AI suggestions, email composer (To/subject/body), channel filters
4. **Web Chat** — customer demo (no internal diagnostics)
5. **Channels** (`/channels` or `/app/channels`) — channel overview, enable/disable, AI mode per channel
6. **Settings → Channel settings** (`/settings/channels`) — detailed email configuration
7. **Customers** — list links to **Customer 360** at `/customers/:id`
8. **Automations** (`/automations`) — list, **New automation**, enable/disable, detail + **execution steps**
9. **Business hours** (`/settings/business-hours`) — editable weekly schedule, timezone, **holidays**
10. **Inbox availability** — Online / Away / Offline dropdown in header
11. **Teams** (`/teams`) — create/edit teams, add/remove members (MANAGER+)

### Demo users

| Role | Name | Email | Password | Teams |
|------|------|-------|----------|-------|
| OWNER | Ava Owner | `owner@example.com` | `agent123!` | — |
| ADMIN | Noah Admin | `admin@example.com` | `agent123!` | — |
| MANAGER | Maya Manager | `manager@example.com` | `agent123!` | Support |
| AGENT | Alex Agent | `agent@example.com` | `agent123!` | Support, Billing |
| AGENT | Priya Shah | `priya.support@example.com` | `agent123!` | Support |
| AGENT | Jordan Lee | `jordan.billing@example.com` | `agent123!` | Billing |
| AGENT | Sam Rivera | `sam.both@example.com` | `agent123!` | Support, Billing |
| READ_ONLY | Riley Reader | `readonly@example.com` | `agent123!` | — |

**Scenario tips:** login as Maya to manage teams; use Priya + Alex + Sam for Support round-robin; Jordan for Billing-only; Riley to confirm read-only 403s.

## 5. Day 6 verification

### Migration check

```bash
docker compose exec backend alembic current
# Should show: 0008_day6_automation (head)
```

### List automations

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/automations
```

Expect seeded: Route Billing, Angry Customers, AI Escalation, Reopen on reply, Missed Chat.

### Agent availability (status enum)

```bash
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"ONLINE"}' http://localhost:8000/api/v1/agents/me/availability
```

### Business hours

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/business-hours
```

## 6. Day 4 verification

### Migration check

```bash
docker compose exec backend alembic current
# Should show: 0008_day6_automation (head)
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

### Flow E — Inbound email (mock webhook)

```bash
ORG_ID=$(docker compose exec -T backend python -c "from sqlalchemy import create_engine,select; from sqlalchemy.orm import Session; from app.config import get_settings; from app.infrastructure.database.models import Organization; e=create_engine(get_settings().database_url_sync); print(Session(e).scalar(select(Organization.id).limit(1)))")

curl -s -X POST http://localhost:8000/api/v1/webhooks/email/inbound \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{\"organization_id\":\"$ORG_ID\",\"message_id\":\"<demo-$(date +%s)@example.com>\",\"from_email\":\"demo@example.com\",\"subject\":\"Billing Question\",\"body_text\":\"I need help with my invoice.\"}"
```

Then open **Inbox → Email filter** — conversation appears with AI suggestion (Email mode = Suggest Reply).

### Flow F — Agent email reply

1. Open an EMAIL conversation in Inbox
2. Composer shows read-only **To:** (customer email), subject, body
3. **Send Email** → mock provider records outbound send

### Flow G — Email Suggest → Accept → Send

1. Ensure EMAIL channel mode is **Suggest Reply** (Channels page or `PATCH /ai/config`)
2. Send inbound email via mock webhook (Flow E)
3. Wait for AI suggestion in Inbox
4. Click **Use Reply** → composer pre-filled → **Send Email**
5. Automated coverage: `tests/test_day5_email_suggest_accept_send.py`

### Flow H — PATCH channel AI mode

```bash
docker compose exec -T backend python - <<'PY'
import httpx
base = "http://localhost:8000/api/v1"
token = httpx.post(f"{base}/auth/login", json={"email":"agent@example.com","password":"agent123!"}).json()["access_token"]
h = {"Authorization": f"Bearer {token}"}
print(httpx.patch(f"{base}/ai/config", headers=h, json={
    "channel_overrides": [{"channel": "EMAIL", "mode": "SUGGEST_REPLY"}]
}).json()["channel_overrides"])
PY
```

### Flow I — Disabled channel webhook (403)

1. **Channels** → disable Email
2. POST inbound webhook (Flow E) → expect `403 Email channel is disabled`
3. Re-enable before continuing

### Flow J — Attachments

**Upload (agent):**

```bash
# With TOKEN set from login
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/file.pdf" \
  http://localhost:8000/api/v1/attachments
```

**Inbound:** include `attachments` array in webhook payload (base64 content) — see `test_day5_attachments_inbound.py`.

**Outbound:** pass `attachment_ids` in `POST /conversations/{id}/email` body.

Attachment chips appear on messages in Inbox thread view.

## 6. Day 3 demos (still valid)

See previous sections for knowledge search, classification, inbox walkthrough.

## 7. Troubleshooting

- **Gemini 429 on tests**: unset `GEMINI_API_KEY` in `.env`, restart backend/worker
- **No AI reply**: worker running, `enabled=true`, `mode=AUTO_REPLY`, not `HUMAN_CONTROL`
- **Duplicate replies**: idempotency via `processing_key`
- **Evaluation fails with embedding errors**: run eval via Echo path (Settings button uses offline graph when no retrieval DB session in eval runner)
- **Schema docs**: [`docs/database/day6-schema.md`](database/day6-schema.md), [`docs/database/day5-schema.md`](database/day5-schema.md), [`docs/database/day4-schema.md`](database/day4-schema.md)

## 8. Non-Docker (optional)

```bash
cd backend && alembic upgrade head && python -m app.scripts.seed
uvicorn app.main:app --reload --port 8000
celery -A app.workers.celery_app worker --loglevel=info
cd frontend && npm install && npm run dev
```
