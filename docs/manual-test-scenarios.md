# Manual test scenarios — QA checklist

Step-by-step scenarios you can run by hand (UI + curl). Use this after the stack is up; for environment setup see [`run-guide.md`](run-guide.md).

**Pass/fail:** mark each scenario `[ ]` → `[x]` as you go.

---

## 0. Prerequisites (do once)

### 0.1 Start stack

```bash
cd "/path/to/AI Customer Support Platform"
cp .env.example .env   # if needed
docker compose up --build
```

| Must be running | Why |
|-----------------|-----|
| `backend` | API + webhooks |
| `worker` | AI replies, KB ingestion |
| `beat` | Missed chat + SLA checks |
| `frontend` | Agent inbox + `/chat` |
| `postgres`, `redis` | Data + queues |

| URL | Purpose |
|-----|---------|
| http://localhost:5173/login | Agent login |
| http://localhost:5173/chat | Customer web chat |
| http://localhost:8000/docs | Swagger |
| http://localhost:8000/health | Health check |

### 0.2 Demo logins (password `agent123!`)

| Role | Email | Use for |
|------|-------|---------|
| AGENT | `agent@example.com` | Most scenarios |
| MANAGER | `manager@example.com` | Teams / angry routing |
| AGENT (Billing) | `jordan.billing@example.com` | Billing assignment |
| READ_ONLY | `readonly@example.com` | RBAC 403s |
| OWNER | `owner@example.com` | Tickets view=all |

### 0.3 Shell helpers (copy once per terminal)

```bash
export API=http://localhost:8000/api/v1

TOKEN=$(curl -s -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"agent@example.com","password":"agent123!"}' | jq -r .access_token)

ORG_ID=$(docker compose exec -T backend python -c "
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.infrastructure.database.models import Organization
e = create_engine(get_settings().database_url_sync)
print(Session(e).scalar(select(Organization.id).limit(1)))
")

echo "TOKEN=$TOKEN"
echo "ORG_ID=$ORG_ID"
```

### 0.4 Create a web-chat customer (UI)

1. Login as `agent@example.com`
2. **Customers** → create customer (any name/email)
3. Copy the customer **UUID** → `CUSTOMER_ID`
4. Keep this ID for all webchat scenarios (or recreate when needed)

### 0.5 Default seeded AI modes

| Channel | Default mode (API) | UI label |
|---------|-------------------|----------|
| WEB_CHAT | `AUTO_REPLY` | Autopilot |
| EMAIL | `SUGGEST` | Suggest Reply |
| FORM | `DRAFT_ONLY` | Knowledge Base (channel disabled) |

### 0.6 AI mode cheat sheet

| API `mode` | UI name | Customer sees AI message? | Escalates when unsure / no KB? |
|------------|---------|---------------------------|--------------------------------|
| `AUTO_REPLY` | Autopilot | Yes, if confident + grounded | Yes |
| `SUGGEST` | Suggest Reply | No (internal draft only) | Suggestion / escalate path for agents |
| `DRAFT_ONLY` | Knowledge Base | Yes only if grounded on KB | Yes if not grounded |

**Policy knobs (Settings → AI):**

| Setting | ON | OFF |
|---------|----|-----|
| AI Support `enabled` | AI runs | No AI (kill switch) |
| `require_knowledge` | Must find relevant KB or escalate/refuse | May answer without docs |
| `escalate_if_unknown` | Intent `OTHER` escalates | Less aggressive escalation |

---

## 1. Smoke checks

### TC-01 — Stack healthy

**Steps**
1. `curl -s http://localhost:8000/health`
2. Open http://localhost:5173/login → login as agent
3. Confirm Inbox loads

**Expect**
- [ ] Health returns OK
- [ ] Login succeeds
- [ ] Inbox visible

### TC-02 — Worker alive (needed for AI)

**Steps**
1. `docker compose ps` → `worker` is Up
2. Settings → AI Support enabled
3. Settings → **Test** panel → send `"How do I reset my password?"` (or `POST /ai/test`)

**Expect**
- [ ] Worker running
- [ ] Test returns a response / run (not hung forever)

---

## 2. Knowledge base setup (shared for WITH-KB scenarios)

### TC-KB-01 — Ingest FAQ document

**Steps (UI)**
1. Go to **Knowledge**
2. Create source (e.g. type **TEXT**, name `FAQ`)
3. Add document **Password Reset Guide** with body similar to:

```text
Password Reset Guide

To reset your password:
1. Go to the login page
2. Click "Forgot password"
3. Enter your email address
4. Check your inbox for a reset link
5. Click the link and choose a new password

The reset link expires in 24 hours.
If you do not receive the email, check spam or contact support.
```

4. Wait until ingestion status = **COMPLETED** (worker must be running)
5. Optional API search:

```bash
curl -s -X POST "$API/knowledge/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"How do I reset my password?","top_k":5}'
```

**Expect**
- [ ] Document reaches `COMPLETED`
- [ ] Search returns chunks about password reset

### TC-KB-02 — Empty / no relevant KB (for WITHOUT-KB scenarios)

**Steps**
1. Either delete Password Reset docs, **or** ask questions that are clearly out of scope (recommended — leave FAQ in place)
2. Out-of-scope examples:
   - `"Does Acme integrate with XYZ ERP version 99?"`
   - `"What is the CEO's personal phone number?"`

**Expect**
- [ ] Those queries do **not** retrieve strong FAQ hits (or score below threshold)

---

## 2b. Response Policy (greetings / OOD / no-KB)

**Pre:** AI enabled · WEB_CHAT Autopilot · `response_policy_enabled` = ON (default)

### TC-RP-01 — Greeting soft reply

1. `/chat` → send `Hello`
2. Expect customer-visible AI welcome (scope mentioned); **no** AI escalation ticket

### TC-RP-02 — Identity soft reply

1. Send `Who are you?`
2. Expect assistant identity + scope; no ticket

### TC-RP-03 — True OOD soft refuse

1. Send `Does Acme integrate with XYZ ERP version 99?`
2. Expect soft refuse (“outside what I can help” / scope); no ticket when `ood_soft_refuse` ON

### TC-RP-04 — Support + no KB ≠ OOD

1. Ask an in-domain support question with no matching docs (or remove FAQ temporarily)
2. Expect insufficient-knowledge soft refuse (not “out of domain” wording); kind remains support path

### TC-RP-05 — FAQ regression

1. `How do I reset my password?` with FAQ ingested
2. Expect grounded Autopilot reply (unchanged)

### TC-RP-06 — Kill switch

1. Settings → uncheck **Response policy enabled** → Save
2. Send `Hello` → legacy escalate / ticket path
3. Re-enable policy when done

---

## 3. Web chat — Autopilot + knowledge

### TC-WC-01 — Autopilot WITH knowledge (grounded reply)

**Pre:** TC-KB-01 done · WEB_CHAT mode = Autopilot · AI enabled · `require_knowledge` = ON

**Steps**
1. Open http://localhost:5173/chat (no agent login)
2. Paste `CUSTOMER_ID`
3. Send: `How do I reset my password?`
4. Wait ~5–30s for AI (worker)
5. In another tab, login → **Inbox** → open the conversation
6. Open AI Information / run detail if shown

**Expect**
- [ ] Customer chat shows an AI reply that mentions forgot-password / reset steps
- [ ] Conversation stays AI-controlled (not forced to human unless policy fails)
- [ ] Inbox shows the same customer-visible reply
- [ ] Run/trace shows retrieval hits on Password Reset Guide (when Gemini or Echo path provides grounding metadata)

**Curl alternative**

```bash
# Start
CONV=$(curl -s -X POST "$API/public/conversations" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"channel\":\"WEB_CHAT\",\"initial_message\":\"How do I reset my password?\"}")
echo "$CONV" | jq .
CONV_ID=$(echo "$CONV" | jq -r .id)

# Poll messages
sleep 8
curl -s "$API/public/conversations/$CONV_ID/messages?customer_id=$CUSTOMER_ID" | jq .
```

### TC-WC-02 — Autopilot WITHOUT knowledge (escalation)

**Pre:** AI enabled · Autopilot · `require_knowledge` = ON · `escalate_if_unknown` = ON (defaults)

**Steps**
1. `/chat` → same or new customer
2. Send: `Does your product integrate with XYZ ERP version 99?`
3. Wait for processing
4. Check **Inbox** + **Tickets**

**Expect**
- [ ] No confident grounded auto-answer (or escalation notice path)
- [ ] Conversation moves toward waiting for agent / handoff
- [ ] Ticket created with source **`AI_ESCALATION`**
- [ ] Automation **AI Escalation** may notify Support (bell / Automations executions)

### TC-WC-03 — Autopilot with `require_knowledge` OFF

**Steps**
1. Settings → uncheck **Require knowledge** → Save
2. `/chat` → ask out-of-scope question again
3. Observe reply vs escalation
4. **Re-enable Require knowledge** when done

**Expect**
- [ ] AI may reply without citations (Echo/Gemini improvisation) — higher hallucination risk
- [ ] Escalation less likely for “no KB hit” alone

### TC-WC-04 — Suggest Reply mode (web chat)

**Steps**
1. Settings → Mode → **Suggest Reply** (`SUGGEST`) → Save  
   (or Channels → WEB_CHAT → Suggest Reply)
2. `/chat` → `How do I reset my password?`
3. Customer chat: wait — should **not** see AI answer as customer message
4. Agent Inbox → open thread → find **suggestion** → **Use Reply** → Send

**Expect**
- [ ] Customer UI has no auto AI message
- [ ] Inbox shows internal suggestion
- [ ] After Use Reply + Send, customer sees agent message

**Restore:** set WEB_CHAT back to **Autopilot** for later tests.

```bash
curl -s -X PATCH "$API/ai/config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"AUTO_REPLY","channel_overrides":[{"channel":"WEB_CHAT","mode":"AUTO_REPLY"}]}'
```

### TC-WC-05 — Knowledge Base mode (`DRAFT_ONLY`) WITH KB

**Steps**
1. Set WEB_CHAT mode to **Knowledge Base** (`DRAFT_ONLY`)
2. Ask password reset question (KB present)
3. Confirm customer gets grounded reply when retrieval succeeds

**Expect**
- [ ] Grounded answer sent when KB hits are good

### TC-WC-06 — Knowledge Base mode WITHOUT KB

**Steps**
1. Keep `DRAFT_ONLY` + `require_knowledge` ON
2. Ask out-of-scope question
3. Check ticket / escalation

**Expect**
- [ ] No customer-facing guessed answer
- [ ] Escalation / ticket (`AI_ESCALATION`)

**Restore Autopilot** after this block.

### TC-WC-07 — Kill switch

**Steps**
1. Settings → disable **AI Support**
2. `/chat` → send any question
3. Re-enable AI

**Expect**
- [ ] No AI auto-reply / offline or waiting behavior
- [ ] After re-enable, AI works again

### TC-WC-08 — Takeover / return to AI

**Pre:** Autopilot ON, conversation open with AI control

**Steps**
1. Inbox → open live chat conversation
2. **Takeover** (or curl below)
3. Send another customer message from `/chat`
4. Confirm AI does **not** auto-reply under human control
5. **Return to AI**
6. Customer sends again → AI may reply again

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$API/conversations/$CONV_ID/takeover"

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$API/conversations/$CONV_ID/return-to-ai"
```

**Expect**
- [ ] `HUMAN_CONTROL` blocks Autopilot sends
- [ ] Return to AI restores Autopilot behavior

### TC-WC-09 — Follow-up messages (same conversation)

**Steps**
1. Start chat with password question → get AI reply
2. Send follow-up: `The reset email never arrived`
3. Confirm same `conversation_id` continues (localStorage / Inbox)

**Expect**
- [ ] Same thread in Inbox
- [ ] Second AI/agent response appears in-thread

---

## 4. Email — inbound curl + AI modes

### Shared: send inbound email

```bash
MSG_ID="demo-$(date +%s)@example.com"

curl -s -X POST "$API/webhooks/email/inbound" \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{
    \"organization_id\": \"$ORG_ID\",
    \"message_id\": \"$MSG_ID\",
    \"from_email\": \"customer.demo@example.com\",
    \"from_name\": \"Demo Customer\",
    \"to_email\": \"support@acme.example\",
    \"subject\": \"Help with password\",
    \"body_text\": \"How do I reset my password?\"
  }" | jq .
```

Save returned `conversation_id` as `EMAIL_CONV_ID`.

### TC-EM-01 — Inbound email appears in Inbox (default Suggest)

**Pre:** Email channel **enabled** · mode **Suggest Reply** (seed default)

**Steps**
1. Run inbound curl above
2. Inbox → filter **Email**
3. Open conversation

**Expect**
- [ ] Response JSON: `"status":"ok"`, `duplicate: false`
- [ ] Conversation channel = EMAIL
- [ ] Customer message body visible
- [ ] AI **suggestion** appears for agent (not auto-sent as outbound email)

### TC-EM-02 — Email Suggest → Accept → Send

**Steps**
1. From TC-EM-01, click **Use Reply**
2. Composer shows **To:** (customer), subject, body
3. **Send Email**

**Expect**
- [ ] Outbound email recorded (mock provider)
- [ ] Thread shows agent/outbound message
- [ ] Customer-facing content matches accepted suggestion (or edited text)

**API outbound (optional)**

```bash
curl -s -X POST "$API/conversations/$EMAIL_CONV_ID/email" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Re: Help with password","content":"Here are the reset steps...","attachment_ids":[]}' | jq .
```

### TC-EM-03 — Email WITH knowledge (Knowledge Base / Autopilot)

**Pre:** TC-KB-01 completed

**Set EMAIL to Knowledge Base or Autopilot**

```bash
# Knowledge Base mode (grounded send or escalate)
curl -s -X PATCH "$API/ai/config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_overrides":[{"channel":"EMAIL","mode":"DRAFT_ONLY"}]}' | jq .

# OR Autopilot
curl -s -X PATCH "$API/ai/config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_overrides":[{"channel":"EMAIL","mode":"AUTO_REPLY"}]}' | jq .
```

**Steps**
1. Inbound email with body: `How do I reset my password?` (new unique `message_id`)
2. Wait for worker
3. Inbox → Email thread

**Expect (DRAFT_ONLY / AUTO_REPLY + good KB)**
- [ ] AI produces grounded answer
- [ ] Autopilot: outbound/auto path when confident
- [ ] Knowledge Base mode: send only when grounded; else escalate

### TC-EM-04 — Email WITHOUT knowledge (escalation)

**Pre:** EMAIL = `DRAFT_ONLY` or `AUTO_REPLY` · `require_knowledge` ON

**Steps**
1. Inbound:

```bash
curl -s -X POST "$API/webhooks/email/inbound" \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{
    \"organization_id\": \"$ORG_ID\",
    \"message_id\": \"unknown-$(date +%s)@example.com\",
    \"from_email\": \"lost@example.com\",
    \"subject\": \"Weird request\",
    \"body_text\": \"Does your product integrate with XYZ ERP version 99?\"
  }" | jq .
```

2. Check Tickets + Inbox

**Expect**
- [ ] Escalation ticket `AI_ESCALATION` (or waiting for agent)
- [ ] No confident fabricated outbound as “resolved”

### TC-EM-05 — Restore EMAIL to Suggest Reply

```bash
curl -s -X PATCH "$API/ai/config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel_overrides":[{"channel":"EMAIL","mode":"SUGGEST"}]}' | jq .
```

- [ ] Channels / Settings show Email = Suggest Reply

### TC-EM-06 — Duplicate webhook (idempotency)

**Steps**
1. Send inbound with fixed `message_id` e.g. `dup-test-001@example.com`
2. Send **exact same** payload again

**Expect**
- [ ] First: `duplicate: false`
- [ ] Second: `duplicate: true`, same conversation

### TC-EM-07 — Email channel disabled → 403

**Steps**
1. **Channels** / Settings → disable **Email**
2. POST inbound webhook again
3. Re-enable Email

**Expect**
- [ ] `403` with message about email channel disabled
- [ ] After re-enable, inbound works again

### TC-EM-08 — Email threading (reply)

**Steps**
1. Create inbound email → note conversation
2. Agent sends outbound email (TC-EM-02)
3. Customer reply webhook with `in_reply_to` = prior outbound `external_message_id` / Message-ID

```bash
# Replace IN_REPLY_TO with the outbound external message id from the thread
curl -s -X POST "$API/webhooks/email/inbound" \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{
    \"organization_id\": \"$ORG_ID\",
    \"message_id\": \"reply-$(date +%s)@example.com\",
    \"from_email\": \"customer.demo@example.com\",
    \"subject\": \"Re: Help with password\",
    \"body_text\": \"Thanks, I found the email.\",
    \"in_reply_to\": \"<IN_REPLY_TO>\"
  }" | jq .
```

**Expect**
- [ ] Same `conversation_id` (threaded), not a brand-new unrelated ticket thread

### TC-EM-09 — Inbound attachment

```bash
B64=$(echo -n "invoice line items" | base64 -w0)

curl -s -X POST "$API/webhooks/email/inbound" \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{
    \"organization_id\": \"$ORG_ID\",
    \"message_id\": \"att-$(date +%s)@example.com\",
    \"from_email\": \"billing@example.com\",
    \"subject\": \"Invoice attached\",
    \"body_text\": \"Please see attached.\",
    \"attachments\": [{
      \"filename\": \"invoice.txt\",
      \"mime_type\": \"text/plain\",
      \"content_base64\": \"$B64\"
    }]
  }" | jq .
```

**Expect**
- [ ] Message shows attachment chip in Inbox

### TC-EM-10 — Billing-intent email → automation routing

**Steps**
1. Ensure agents ONLINE (header dropdown or curl)
2. Inbound subject/body about invoice/billing

```bash
curl -s -X POST "$API/webhooks/email/inbound" \
  -H "Content-Type: application/json" \
  -H "x-mock-signature: test-bypass" \
  -d "{
    \"organization_id\": \"$ORG_ID\",
    \"message_id\": \"bill-$(date +%s)@example.com\",
    \"from_email\": \"payer@example.com\",
    \"subject\": \"Billing Question\",
    \"body_text\": \"I need help with my invoice and last charge.\"
  }" | jq .
```

3. Check Automations → **Route Billing** executions; team/priority/tags

**Expect**
- [ ] Billing team / HIGH priority / related tag when classifier marks BILLING
- [ ] Notification may appear for team members

---

## 5. Matrix — quick WITH / WITHOUT knowledge

Use this as a coverage grid. Run after TC-KB-01.

| # | Channel | Mode | Knowledge | Ask | Expected |
|---|---------|------|-----------|-----|----------|
| M1 | Web chat | Autopilot | WITH FAQ | Password reset | Customer AI reply |
| M2 | Web chat | Autopilot | WITHOUT (unknown Q) | XYZ ERP | Escalate + ticket |
| M3 | Web chat | Knowledge Base | WITH FAQ | Password reset | Grounded send |
| M4 | Web chat | Knowledge Base | WITHOUT | Unknown | Escalate, no guess |
| M5 | Web chat | Suggest | WITH FAQ | Password reset | Inbox suggestion only |
| M6 | Email | Suggest | WITH FAQ | Password reset | Suggestion → accept → send |
| M7 | Email | Autopilot | WITH FAQ | Password reset | Auto path when confident |
| M8 | Email | Knowledge Base | WITHOUT | Unknown | Escalate |
| M9 | Either | Any | Kill switch OFF | Anything | No AI processing |
| M10 | Either | Autopilot | `require_knowledge` OFF + unknown | Unknown | May answer without KB |

- [ ] M1  - [ ] M2  - [ ] M3  - [ ] M4  - [ ] M5
- [ ] M6  - [ ] M7  - [ ] M8  - [ ] M9  - [ ] M10

---

## 6. Automations, SLA, missed chat

### TC-AU-01 — Angry customer

**Steps**
1. Web chat or email with angry tone (intensity / hostility — not only keyword lists), e.g.  
   `This is ridiculous — fix your mess. I'm done waiting.`  
   or `now i get angry`  
   (Also still OK: `This is the third time I've contacted you!`)
2. Check Automations executions → **Angry Customers**
3. Check priority / manager notify

**Expect**
- [ ] Priority **URGENT** (or configured action)
- [ ] Manager notification path fires

### TC-AU-02 — Missed chat

**Pre:** beat running · note `missed_chat_timeout_minutes` in AI config (default often **5**)

**Steps**
1. Set agent availability **OFFLINE** (or leave unanswered)
2. Start web chat, send message, **do not** reply as agent / let AI fail to answer in time per product rules
3. Wait past timeout (+ beat cycle ~60s)
4. Check ticket source **`MISSED_CHAT`** / Missed Chat automation

**Expect**
- [ ] Missed-chat ticket or automation execution appears

### TC-AU-03 — SLA (high/urgent)

**Steps**
1. Trigger billing/angry path so priority becomes HIGH or URGENT
2. Leave without first response past SLA (seed: High ~30m, Urgent ~15m — shorten only if you change policies for QA)
3. Or inspect SLA timers via tickets/API after priority set

**Expect**
- [ ] SLA timer attached on priority change
- [ ] Breach processing depends on beat (long wait unless policies shortened for lab)

### TC-AU-04 — Reopen on reply

**Steps**
1. Close a conversation/ticket that supports reopen automation
2. Customer sends a new message on that thread
3. Check **Reopen on reply** execution

**Expect**
- [ ] Conversation/ticket reopens per rule

---

## 7. Agent / inbox / tickets

### TC-IN-01 — Manual ticket from conversation

**Steps**
1. Open conversation → create ticket (UI or `POST /conversations/{id}/ticket`)
2. Tickets list → open ticket

**Expect**
- [ ] Ticket source `AGENT_CREATED` (or equivalent)
- [ ] Linked to conversation

### TC-IN-02 — Ticket views (RBAC)

**Steps**
1. As agent: `Tickets` → Mine / Team / Unassigned
2. As `readonly@example.com`: attempt write actions
3. As owner: view **All**

**Expect**
- [ ] Agents see team-scoped data
- [ ] Read-only cannot mutate (403)
- [ ] Owner/Admin can use All

### TC-IN-03 — Notifications bell

**Steps**
1. Trigger AI Escalation or Route Billing
2. Open header notification bell
3. Mark read / deep-link

**Expect**
- [ ] Notification appears
- [ ] Mark read works

### TC-IN-04 — Availability

```bash
curl -s -X PATCH "$API/agents/me/availability" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"ONLINE"}'
```

Cycle ONLINE → AWAY → OFFLINE in UI.

**Expect**
- [ ] Status persists and affects assignment / missed chat behavior

---

## 8. Channels & settings

### TC-CH-01 — Channel enable/disable

**Steps**
1. Disable WEB_CHAT → try public chat/API
2. Re-enable
3. Confirm FORM stays disabled (no public form UI)

**Expect**
- [ ] Disabled channel rejects or blocks intake
- [ ] FORM remains offline in demo

### TC-CH-02 — AI evaluation suite

**Steps**
1. Settings → **Run evaluation suite**
2. Or: `POST /ai/evaluations/run` with Bearer token

**Expect**
- [ ] Suite runs and returns case results (pass/fail summary)

### TC-CH-03 — Business hours

**Steps**
1. `/settings/business-hours` → view schedule / holidays
2. Optionally edit and save

**Expect**
- [ ] Schedule loads and saves

---

## 9. Full inbound email payload reference

```json
{
  "organization_id": "<uuid>",
  "message_id": "<unique-id@example.com>",
  "from_email": "john@example.com",
  "from_name": "John Doe",
  "to_email": "support@acme.example",
  "subject": "Password Reset",
  "body_text": "I cannot reset my password.",
  "body_html": "<p>optional</p>",
  "in_reply_to": "<prior-message-id@example.com>",
  "references": ["<root@example.com>"],
  "attachments": [
    {
      "filename": "invoice.txt",
      "mime_type": "text/plain",
      "content_base64": "<base64>"
    }
  ]
}
```

Auth for mock provider: header `x-mock-signature: test-bypass`  
(or HMAC of body with `EMAIL_WEBHOOK_SECRET`).

---

## 10. Public webchat API reference

```bash
# Create
curl -s -X POST "$API/public/conversations" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"channel\":\"WEB_CHAT\",\"initial_message\":\"Hello\"}"

# Follow-up
curl -s -X POST "$API/public/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"content\":\"Still need help\"}"

# List
curl -s "$API/public/conversations/$CONV_ID/messages?customer_id=$CUSTOMER_ID"

# AI timeout check (used by UI polling)
curl -s -X POST "$API/public/conversations/$CONV_ID/check-ai-response" \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"$CUSTOMER_ID\",\"message_id\":\"$MSG_ID\"}"
```

---

## 11. Recommended order (half-day QA pass)

1. TC-01, TC-02  
2. TC-KB-01  
3. Matrix M1, M2 (webchat WITH/WITHOUT KB)  
4. TC-WC-04 Suggest; TC-WC-07 Kill switch; TC-WC-08 Takeover  
5. TC-EM-01 → TC-EM-02 → TC-EM-03 → TC-EM-04 → TC-EM-05  
6. TC-EM-06, TC-EM-07, TC-EM-09  
7. TC-AU-01, TC-EM-10  
8. TC-IN-02, TC-IN-03  
9. TC-CH-02 evaluation suite  

---

## 12. Troubleshooting (manual QA)

| Symptom | Check |
|---------|--------|
| No AI reply | `worker` up; AI enabled; not HUMAN_CONTROL; mode Autopilot for auto-send |
| KB stuck PENDING | `worker` up; document retry in Knowledge UI |
| Email 403 | Channel enabled; `x-mock-signature: test-bypass`; `organization_id` set |
| Weak / wrong retrieval | Empty `GEMINI_API_KEY` uses lexical/Echo — still OK for demos; set key for semantic quality |
| Duplicate weirdness | Always use unique `message_id` per new email |
| Missed chat never fires | `beat` service running; wait > timeout |

---

## Related docs

- [`run-guide.md`](run-guide.md) — setup, Flows A–J, pytest suites  
- [`progress.md`](progress.md) — demo users & feature status  
- [`codebase-map.md`](codebase-map.md) — where code lives  
- API Explorer: http://localhost:8000/docs  
