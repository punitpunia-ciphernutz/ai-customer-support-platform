# Day 5 — Omnichannel schema

**Migration:** `0007_day5_omnichannel`  
**Depends on:** Day 4 (`0005_day4_ai_reliability`), `0006_ai_response_timeout`

## New enum: `delivery_status`

| Value | Meaning |
|-------|---------|
| `QUEUED` | Outbound message persisted, not yet sent |
| `SENDING` | Provider send in progress |
| `SENT` | Provider accepted send |
| `DELIVERED` | Provider delivery confirmation (optional) |
| `OPENED` | Open tracking (optional, provider-dependent) |
| `FAILED` | Send failed |

## Extended: `messages`

| Column | Type | Purpose |
|--------|------|---------|
| `channel` | `channel_type` (nullable) | Origin channel for cross-channel timelines |
| `external_message_id` | `varchar(512)` | Provider Message-ID for threading + idempotency |
| `delivery_status` | `delivery_status` (nullable) | Outbound lifecycle |

**Index:** `ix_messages_external_message_id`

## Extended: `conversations`

| Column | Type | Purpose |
|--------|------|---------|
| `thread_id` | `varchar(512)` | Root email thread identifier |

**Index:** `ix_conversations_thread_id`

## New: `external_messages`

Idempotency for inbound webhooks.

| Column | Type | Notes |
|--------|------|-------|
| `organization_id` | UUID FK | Tenant scope |
| `provider` | varchar(64) | e.g. `resend`, `mock` |
| `external_message_id` | varchar(512) | Provider message id |
| `message_id` | UUID FK → messages | Created message |

**Unique:** `(organization_id, provider, external_message_id)`

## New: `attachments`

| Column | Type | Notes |
|--------|------|-------|
| `message_id` | UUID FK | Parent message |
| `filename` | varchar(512) | Display name |
| `mime_type` | varchar(128) | Content type |
| `size` | integer | Bytes |
| `storage_key` | varchar(1024) | Object storage key |
| `metadata` | JSONB | Extra fields |

**Download:** Files live in object storage (`STORAGE_ROOT_DIR`, default `/tmp/support-attachments`). In Docker Compose this directory is a named volume (`attachment_uploads`) so files survive container restarts. Browsers must not use `file://` paths. Agents download via authenticated:

- `GET /api/v1/attachments/{id}` → metadata + `download_url`
- `GET /api/v1/attachments/{id}/download` → file bytes (`Content-Disposition: attachment`)

`download_url` is the API path `/api/v1/attachments/{id}/download` (requires `conversations:read` bearer token). If the DB row exists but the blob is missing (e.g. wiped ephemeral disk), download returns `404 Attachment file missing`.

## New: `channel_configurations`

Per-org channel settings (no plaintext secrets).

| Column | Type | Notes |
|--------|------|-------|
| `organization_id` | UUID FK | Tenant |
| `channel` | `channel_type` | WEB_CHAT, EMAIL, FORM |
| `enabled` | boolean | Channel active |
| `provider` | varchar(64) | Email provider name |
| `settings` | JSONB | Non-secret config (from address, domain, etc.) |

**Unique:** `(organization_id, channel)`

### EMAIL `settings` keys — auto-responder

Stored in `channel_configurations.settings` (no migration; JSONB). Updated via `PATCH /api/v1/channels/EMAIL` (shallow-merged into existing settings).

| Key | Type | Purpose |
|-----|------|---------|
| `email_auto_reply_enabled` | bool | When true, send a receipt email on the first customer message of a new email thread |
| `email_auto_reply_subject` | string | Subject template (default: `We received your message`) |
| `email_auto_reply_body` | text | Body template |

**Placeholders:** `{{customer_name}}`, `{{customer_email}}`, `{{subject}}`, `{{conversation_id}}`, `{{ticket_id}}` (empty until a ticket exists).

**Runtime:** `EmailAutoResponderService` runs after inbound email persistence. Guardrails: first customer message only; skip when inbound `Auto-Submitted` / bounce-like headers or mailer-daemon; skip if an auto-responder was already sent for the conversation; outbound sets `Auto-Submitted: auto-replied`.

**UI:** Settings → Channels → Email Auto-Responder.

## Query patterns

- **Thread lookup:** `messages.external_message_id IN (in_reply_to, references...)`
- **Idempotency:** `SELECT FROM external_messages WHERE org + provider + external_message_id`
- **Subject fallback:** `conversations WHERE customer_id + normalized_subject + channel=EMAIL`
- **Attachments:** `attachments WHERE message_id = ?`

## Rollback

`alembic downgrade 0006_ai_response_timeout` drops new tables and message/conversation columns.
