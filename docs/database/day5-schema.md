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

## Query patterns

- **Thread lookup:** `messages.external_message_id IN (in_reply_to, references...)`
- **Idempotency:** `SELECT FROM external_messages WHERE org + provider + external_message_id`
- **Subject fallback:** `conversations WHERE customer_id + normalized_subject + channel=EMAIL`
- **Attachments:** `attachments WHERE message_id = ?`

## Rollback

`alembic downgrade 0006_ai_response_timeout` drops new tables and message/conversation columns.
