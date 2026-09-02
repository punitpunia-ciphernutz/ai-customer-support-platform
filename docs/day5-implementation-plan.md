# Day 5 Implementation Plan — Email + Omnichannel Foundation + Unified Inbox

**Goal:** Prove the platform is not Web Chat–specific. Bring Email into the same Conversation / Message / AI / Ticket pipeline without building a separate email system.

**Principle:** Channels are adapters. Conversations are the core. AI operates on conversations, not channels.

**Rule:** Extend Days 1–4 architecture (adapters, `ConversationService`, LangGraph AI, Celery, event bus). Implement one email provider behind an interface. Do not hard-code Gmail/SendGrid/SES throughout the app.

**Depends on:** Day 4 complete (`RuntimeAIConfig`, bot modes, escalation, suggestion lifecycle, inbox UI, `BotConfiguration` per channel).

**Status:** **COMPLETE** (2026-09-02) — migration `0007_day5_omnichannel`, 16/16 Day 5 tests, 26/26 Day 4 regression tests.

## Target architecture

```
CUSTOMER
   │
   ├── WEB CHAT ──► WebChatAdapter ──┐
   └── EMAIL ─────► EmailAdapter ─────┤
                                      ▼
                            MessageNormalizer
                                      │
                                      ▼
                              Conversation Core
                                      │
                         ┌────────────┴────────────┐
                       HUMAN                      AI
                         │                         │
                         └────────────┬────────────┘
                                      ▼
                              Unified Inbox
                                      │
                                      ▼
                                   Ticket
```

---

## Existing hooks (extend, don't fork)

| Area | Path |
|------|------|
| Channel adapter ABC + stubs | `backend/app/modules/conversations/channels.py` |
| Conversation orchestration | `backend/app/modules/conversations/service.py` |
| `ChannelType` enum (`WEB_CHAT`, `EMAIL`, `FORM`) | `backend/app/infrastructure/database/models.py` |
| Per-channel AI config | `backend/app/modules/ai/application/runtime_config.py`, `BotConfiguration` |
| AI orchestration | `backend/app/modules/ai/application/ai_service.py` |
| Celery worker pattern | `backend/app/workers/tasks.py` |
| Event bus + WS inbox | `backend/app/infrastructure/events/bus.py`, `modules/inbox/ws.py` |
| Inbox UI | `frontend/src/features/inbox/InboxPage.tsx` |
| Settings (channel mode display) | `frontend/src/features/settings/SettingsPage.tsx` |
| Customers | `backend/app/modules/customers/` |
| Seed channel overrides | `backend/app/scripts/seed.py` (EMAIL=SUGGEST, FORM=KNOWLEDGE_BASE) |

**Already stubbed:** `EmailAdapter`, `FormAdapter` — all methods raise `NotImplementedError`.

---

## Recommended implementation order (critical path)

```
1.  DB migration (Message extensions, Attachment, ExternalMessage/idempotency, ChannelConfiguration)
2.  Object storage abstraction (S3-compatible; MinIO/local for dev)
3.  Normalized channel events + event bus wiring
4.  CustomerResolver (email → customer; auth user → customer)
5.  EmailProvider abstraction + one provider (Resend or SendGrid)
6.  EmailAdapter (normalize, identify, receive, send)
7.  Inbound webhook (signature verify → adapter → idempotency → ConversationService)
8.  Email threading (Message-ID, In-Reply-To, References, subject fallback)
9.  Outbound email via adapter (agent + AI paths) + delivery status lifecycle
10. Attachment foundation (upload, metadata, UI display)
11. Wire AI outbound through MessageService → EmailAdapter (not direct LLM send)
12. Validate per-channel bot modes on EMAIL (Suggest / Autopilot / Knowledge Base)
13. Channel settings API + PATCH bot overrides
14. Unified Inbox (channel badges, filters, cross-channel timeline)
15. Email composer + AI suggestion UI for email conversations
16. Customer 360 (cross-channel conversations, timeline)
17. Ticket integration validation (email escalation, agent create, source/channel fields)
18. Day 5 acceptance tests + Definition of Done
```

---

## Phase 1 — Database & domain models

**Unlocks:** idempotency, threading metadata, attachments, channel config, delivery tracking

### New / extended entities

| Entity | Purpose |
|--------|---------|
| `Message` extensions | `channel`, `external_message_id`, `delivery_status`, richer `metadata` (email headers) |
| `ExternalMessage` (or unique index) | Idempotency key: `(organization_id, provider, external_message_id)` |
| `Attachment` | `message_id`, `filename`, `mime_type`, `size`, `storage_key`, `metadata` |
| `ChannelConfiguration` | Per-org channel: `enabled`, `provider`, `settings` (JSONB; no plaintext secrets) |
| `Conversation` extensions (optional) | `thread_id` / email thread metadata in `metadata` or dedicated column |

### Delivery status enum

```
QUEUED → SENDING → SENT → DELIVERED → OPENED (optional; provider-dependent)
                  └→ FAILED
```

### Alembic

- Migration: `0007_day5_omnichannel.py`
- Document in `docs/database/day5-schema.md`

### Tasks

- [x] SQLAlchemy models + Pydantic schemas
- [x] Unique constraint on `(org_id, provider, external_message_id)` for idempotency
- [x] Index on `Message.external_message_id` for threading lookups
- [x] Seed: default `ChannelConfiguration` for EMAIL (disabled until configured)

---

## Phase 2 — Infrastructure abstractions

### Object storage (`ObjectStorage`)

```
ObjectStorage
├── upload(key, data, content_type) → storage_key
├── download(key) → bytes
├── delete(key)
└── generate_url(key, expires) → presigned URL
```

- [x] ABC in `backend/app/infrastructure/storage/`
- [x] S3-compatible implementation (MinIO for local dev via docker-compose)
- [x] Settings: `STORAGE_ENDPOINT`, `STORAGE_BUCKET`, credentials via env/secrets

### Normalized channel events

| Event | When |
|-------|------|
| `message.received` | Inbound webhook processed |
| `message.sent` | Outbound persisted + handed to provider |
| `message.delivered` | Provider callback (if supported) |
| `message.failed` | Send failure |

Payload: `channel`, `provider`, `external_message_id`, `conversation_id`, `message_id`, `metadata`.

- [x] Event dataclasses in `backend/app/modules/conversations/events.py` (or extend event bus)
- [x] Publish from webhook handler and outbound send path
- [x] WS fan-out to inbox on `message.received` / status changes

### Webhook architecture (no provider logic in conversation controller)

```
POST /webhooks/email/inbound
  → EmailWebhookHandler
  → EmailProvider.verify() + parse()
  → EmailAdapter.normalize()
  → IncomingMessageEvent
  → ConversationService.receive_inbound()
```

- [x] Dedicated `backend/app/modules/channels/` or `conversations/webhooks.py`
- [x] Register in `backend/app/api/router.py`

---

## Phase 3 — Email provider abstraction

### `EmailProvider` interface

```
EmailProvider
├── receive(payload) → raw parsed dict
├── send(to, subject, body, headers, attachments) → external_message_id
├── parse(payload) → normalized inbound fields
├── verify(request) → bool  (signature)
└── normalize(raw) → provider-agnostic dict
```

- [x] ABC + factory in `backend/app/infrastructure/email/`
- [x] **One provider for Day 5** (Resend recommended — simple webhook + send API)
- [x] Provider selected via `ChannelConfiguration.provider` or env default
- [x] Credentials from env/secret store only — never in `ChannelConfiguration.configuration` plaintext

---

## Phase 4 — Channel adapters & message normalization

### Refine adapter layer

```
WebChatAdapter   (existing — keep send as WS fan-out)
EmailAdapter     (implement fully)
FormAdapter      (minimal stub OK if not in Day 5 tests; keep interface)
```

### `MessageNormalizer`

Single internal shape regardless of channel:

```json
{
  "channel": "EMAIL",
  "sender_type": "CUSTOMER",
  "content": "...",
  "external_message_id": "msg_123",
  "metadata": { "subject": "...", "headers": {...} }
}
```

- [x] Implement `EmailAdapter.receive/normalize/identify_customer/send`
- [x] Extend `ConversationService` with `receive_inbound(normalized_message)` used by all adapters
- [x] Ensure AI receives `SupportMessage` / conversation messages — not channel-specific types
- [x] Refactor WebChat path to use same `receive_inbound` entry point where practical

### `CustomerResolver`

```
Email address → existing Customer? → use
              → else → create Customer
Authenticated user ID (Web Chat) → Customer
```

- [x] `backend/app/modules/customers/resolver.py`
- [x] Called from `EmailAdapter.identify_customer()` and WebChat when email present
- [x] No fuzzy matching on Day 5

---

## Phase 5 — Inbound email pipeline

### Webhook: `POST /api/v1/webhooks/email/inbound`

1. Verify provider signature
2. Parse sender, recipient, subject, body, attachment metadata
3. **Idempotency check** — `(provider, external_message_id)` already processed → return 200, no-op
4. Resolve customer via `CustomerResolver`
5. **Thread resolution** (priority order):
   - `In-Reply-To` / `References` → match stored `Message.external_message_id`
   - Conversation thread metadata
   - Fallback: `customer + normalized subject` (strip `Re:` / `Fwd:`)
6. Create conversation if none found; set/update `subject`
7. Create message + attachment records (files → object storage)
8. Enqueue AI processing (existing Celery pattern)
9. Emit `message.received`

- [x] Idempotency table/service — duplicate webhook → 1 customer, 1 conversation, 1 message
- [x] Async processing option via Celery for heavy attachment uploads

---

## Phase 6 — Outbound email & delivery status

### Agent reply: `POST /api/v1/conversations/{id}/email`

### Generic message: `POST /api/v1/conversations/{id}/messages` (channel-aware send)

Flow:

```
Agent / AI
  → MessageService.create_outbound()
  → delivery_status = QUEUED
  → EmailAdapter.send()
  → provider send with threading headers
  → SENT (+ external_message_id stored)
  → on failure: FAILED
```

### Email threading headers (outbound)

- [x] Set `Message-ID`, `In-Reply-To`, `References` from conversation thread
- [x] Subject: `Re: {conversation.subject}`
- [x] Customer reply must land in **same conversation** (acceptance Test 3)

### AI outbound path (critical)

```
AI decision → resolve
  → MessageService (not ai_service direct send)
  → EmailAdapter.send()
  → EmailProvider
```

- [x] `ai_service.py` already mode-gated — ensure AUTO_REPLY calls adapter send for EMAIL channel
- [x] SUGGEST_REPLY: suggestion in metadata; agent accepts → opens composer → send

---

## Phase 7 — Attachments foundation

Day 5 scope: metadata + storage + UI display — not full document AI processing.

### `Attachment` model

```
id, message_id, filename, mime_type, size, storage_key, metadata
```

### APIs

| Method | Path |
|--------|------|
| `POST` | `/api/v1/attachments` (upload → object storage) |
| `GET` | `/api/v1/attachments/{id}` (metadata + download URL) |

- [x] Inbound: extract attachment metadata from webhook; store files via `ObjectStorage`
- [x] Outbound: attach files on email send (provider API)
- [x] UI: show attachment chip/link in `MessageBubble.tsx`

---

## Phase 8 — Channel-agnostic AI & per-channel bot modes

Validate existing Day 4 modes on EMAIL channel:

| Channel | Default (seed) | Day 5 validation |
|---------|----------------|------------------|
| Web Chat | AUTOPILOT | unchanged |
| Email | SUGGEST_REPLY | suggestion UI + composer |
| Form | KNOWLEDGE_BASE | unchanged (stub adapter OK) |

### Email Suggest Reply flow

```
Customer email → AI → suggestion stored on message
  → Agent inbox: [Use Reply] [Edit] [Regenerate] [Discard]
  → Use Reply → pre-fill email composer → agent sends
```

### Email Autopilot flow

```
Known FAQ → grounded answer → confidence > threshold → AI sends via EmailAdapter
Unknown → escalate → ticket + handoff (no hallucination)
```

- [x] Confirm `RuntimeAIConfig.resolve(db, org_id, conversation.channel)` used on email-triggered AI runs
- [x] Reuse existing suggestion accept/reject/regenerate endpoints from Day 4
- [x] Email-specific: "Use Reply" opens composer with suggestion body + subject

---

## Phase 9 — Unified Inbox & Customer 360

### Unified Inbox (`/app/inbox`, `/app/inbox/:conversationId`)

- [x] Channel indicator badges: `WEB CHAT`, `EMAIL`, `FORM`
- [x] Filters: All, My Conversations, Unassigned, Web Chat, Email
- [x] Cross-channel timeline — messages labeled by channel origin
- [x] Email conversations show subject line in list row

### Customer 360 (`/app/customers/:customerId`)

- [x] Single customer view across channels (not duplicate customers per channel)
- [x] Sections: profile, conversations (by channel), tickets, activity timeline
- [x] Link from inbox conversation → customer record

### Channel settings UI (`/app/settings/channels`, `/app/channels`)

- [x] List channels with Connected / Disabled status
- [x] Email: AI mode selector, enable/disable toggle
- [x] Forms: "Coming Soon" placeholder acceptable

---

## Phase 10 — Ticket integration

Validate all paths retain `customer_id`, `conversation_id`, `source`, `channel`:

| Path | Expected |
|------|----------|
| Email → AI escalation | Ticket with `AI_ESCALATION`, channel=EMAIL |
| Web Chat → AI escalation | unchanged |
| Agent → any conversation → create ticket | `source=AGENT`, channel from conversation |

- [x] No regression on Day 4 ticket tests
- [x] Email escalation creates ticket visible in inbox + tickets list

---

## Phase 11 — API summary (Day 5)

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/v1/channels` | List org channel configs |
| `GET` | `/api/v1/channels/{channel}` | Single channel config |
| `PATCH` | `/api/v1/channels/{channel}` | Enable/disable, settings (not secrets) |
| `POST` | `/api/v1/webhooks/email/inbound` | Provider webhook (no auth JWT; signature verify) |
| `POST` | `/api/v1/conversations/{id}/email` | Agent email reply |
| `GET` | `/api/v1/conversations/{id}/messages` | Existing — ensure channel metadata returned |
| `POST` | `/api/v1/conversations/{id}/messages` | Channel-aware outbound |
| `POST` | `/api/v1/attachments` | Upload |
| `GET` | `/api/v1/attachments/{id}` | Metadata + URL |
| `PATCH` | `/api/v1/ai/config` | Extend — PATCH per-channel `BotConfiguration` |

RBAC: webhook unauthenticated (signature only); channel settings require admin; attachments inherit conversation access.

---

## Phase 12 — Frontend screens

| Route | Purpose |
|-------|---------|
| `/app/inbox` | Unified inbox with channel filters |
| `/app/inbox/:conversationId` | Thread view + channel-specific composer |
| `/app/customers/:customerId` | Customer 360 |
| `/app/channels` | Channel overview |
| `/app/settings/channels` | Per-channel config + AI mode |

### Email composer component

- To (read-only from customer)
- Subject (`Re: …`)
- Body (rich text optional; plain text minimum)
- Send button → `POST /conversations/{id}/email`
- AI suggestion panel integration (reuse Day 4 pattern)

- [x] Conditional render: email composer for EMAIL channel; chat composer for WEB_CHAT
- [x] Delivery status indicator on outbound messages (Sent / Failed)

---

## Phase 13 — Day 5 tests

### Suggested test files

- `backend/tests/test_day5_email_inbound.py` — Test 1, Test 7
- `backend/tests/test_day5_email_outbound.py` — Test 2
- `backend/tests/test_day5_email_threading.py` — Test 3
- `backend/tests/test_day5_email_ai_suggest.py` — Test 4
- `backend/tests/test_day5_email_autopilot.py` — Test 5
- `backend/tests/test_day5_email_escalation.py` — Test 6
- `backend/tests/test_day5_customer_resolver.py`
- `backend/tests/test_day5_attachments.py`
- Extend `backend/tests/test_channel_adapter.py` for EmailAdapter

### Acceptance scenarios

| # | Scenario | Expected |
|---|----------|----------|
| 1 | **Inbound email** | Webhook → customer resolved → conversation + message → inbox updated |
| 2 | **Agent email reply** | Agent composes → send → provider called → customer receives |
| 3 | **Email thread** | Customer email → agent reply → customer replies → **same conversation** |
| 4 | **Email + AI Suggest** | EMAIL=SUGGEST → AI suggestion → agent accepts → email sent |
| 5 | **Email Autopilot** | EMAIL=AUTOPILOT → known FAQ → grounded → confidence pass → AI sends email |
| 6 | **Email escalation** | Unknown request → no hallucination → ticket + handoff summary |
| 7 | **Duplicate webhook** | Same payload twice → 1 customer, 1 conversation, 1 message |

Run Day 5 suite:

```bash
pytest tests/test_day5_*.py tests/test_channel_adapter.py -v
```

---

## Definition of Done

### Channel

- [x] Channel abstraction enforced — all inbound/outbound via adapters
- [x] Email adapter fully implemented
- [x] Email provider abstraction + one working provider
- [x] Inbound webhook with signature verification
- [x] Outbound email with threading headers
- [x] Webhook idempotency (external_message_id + provider)
- [x] Delivery status lifecycle on messages
- [x] Attachment foundation (model, storage, API, UI)

### Customer

- [x] Customer resolution by email address
- [x] Cross-channel identity (one customer, multiple channels)
- [x] Unified conversation history on Customer 360

### AI

- [x] Email messages flow through same AI pipeline as Web Chat
- [x] Email Knowledge Base mode works
- [x] Email Suggest Reply mode — suggestion UI + composer send
- [x] Email Autopilot mode — AI sends via adapter
- [x] Email AI escalation → ticket
- [x] AI never sends email directly — always MessageService → EmailAdapter

### Inbox

- [x] Unified Web Chat + Email in one inbox
- [x] Channel filtering and indicators
- [x] Cross-channel conversation timeline
- [x] Email composer
- [x] AI suggestion UI for email conversations

### Ticketing

- [x] Email → ticket (AI escalation)
- [x] Web Chat → ticket (no regression)
- [x] Agent → ticket from any channel
- [x] Tickets retain customer_id, conversation_id, source, channel

### Infrastructure

- [x] Object storage abstraction (not hard-coded AWS calls)
- [x] Normalized channel events published
- [x] Day 5 test suite green
- [x] Schema documented in `docs/database/day5-schema.md`

### Boundary (explicitly out of scope)

- [x] No second email provider (interface only)
- [x] No open/delivery tracking unless provider gives it free
- [x] No fuzzy identity matching
- [x] No attachment AI processing (PDF/DOCX parsing)
- [x] No WhatsApp/Slack/other channels (adapter stubs OK)
- [x] No Help Center / widget (Day 6)

---

## Success demo (end-to-end)

```
CUSTOMER sends email → webhook → CustomerResolver → thread match/create
  → Message (EMAIL) → Celery AI (mode=SUGGEST_REPLY)
  → Agent sees suggestion in unified inbox
  → [Use Reply] → composer → send via EmailAdapter
  → Customer replies → same conversation (threading headers)
  → Switch channel mode to AUTOPILOT → FAQ email → AI sends automatically
  → Unknown question → ticket + handoff → agent sees in inbox + tickets
```

After Day 5, Day 6 adds Help Center + AI Chat Widget + self-service on this foundation.
