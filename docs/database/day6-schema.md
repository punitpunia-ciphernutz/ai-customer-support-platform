# Day 6 — Automation & Routing schema

Migration: `0008_day6_automation`

## New tables

### automations

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| organization_id | UUID | FK → organizations |
| name | varchar(255) | |
| description | text | nullable |
| enabled | boolean | default true |
| trigger | JSONB | `{ "type": "MESSAGE_RECEIVED" }` |
| conditions | JSONB | AND/OR tree, nullable |
| actions | JSONB | array of action configs |
| priority | integer | higher runs first |
| created_by | UUID | FK → users, nullable |
| created_at / updated_at | timestamptz | |

Index: `(organization_id, enabled, priority)`

### automation_executions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| automation_id | UUID | FK |
| organization_id | UUID | FK |
| trigger_event | varchar(128) | e.g. `message.received` |
| entity_type | varchar(64) | conversation, ticket, … |
| entity_id | varchar(64) | |
| status | enum | RUNNING, COMPLETED, FAILED, SKIPPED |
| started_at / completed_at | timestamptz | |
| error | text | nullable |
| metadata | JSONB | execution depth, event id, … |

Index: `(entity_type, entity_id)`

### automation_execution_steps

Per condition/action step with `duration_ms`, `result`, `error`.

### business_hours / business_hours_schedules / business_holidays

Org-level support hours with IANA timezone. Schedule: `day_of_week` 0=Mon..6=Sun, `open_time`, `close_time`, `closed`.

### tags / conversation_tags / ticket_tags

Org-scoped reusable tag catalog plus M2M join tables.

| Table | Purpose |
|-------|---------|
| `tags` | Catalog: unique `(organization_id, name)` (names stored lowercase), optional `color` |
| `conversation_tags` | M2M conversation ↔ tag, unique `(conversation_id, tag_id)` |
| `ticket_tags` | M2M ticket ↔ tag, unique `(ticket_id, tag_id)` |

**API behavior**

- `GET /tags` — org catalog
- `DELETE /tags/{name}` — permanently delete catalog tag and all conversation/ticket links (`tickets.write`)
- `GET|POST /tickets/{id}/tags`, `DELETE /tickets/{id}/tags/{name}` — ticket tag mutations (ACL via ticket visibility; `tickets.read` / `tickets.write`)
- `GET|POST /conversations/{id}/tags`, `DELETE /conversations/{id}/tags/{name}` — conversation tag mutations (`conversations.read` / `conversations.write`)
- `TicketOut.tags` / `ConversationOut.tags` — `tags: string[]` on list/detail payloads
- List filters: `GET /tickets?tag=billing&tag=urgent` (AND), `GET /conversations?tag=…` (AND on effective tags)

**Sync**

Agent tag changes mirror across linked entities: ticket ↔ conversation, and conversation ↔ all tickets for that conversation. Automation `ADD_TAG` / `REMOVE_TAG` also sync conversation tags to all linked tickets (and ticket-only contexts resolve the conversation when possible). Conversation list/detail `tags` are the **effective union** of conversation tags and tags on linked tickets. New tickets (API create, automation `CREATE_TICKET`, AI/agent escalation) inherit existing conversation tags.

**Default intent → tag seeds** (`seed_day6.seed_default_automations`)

| Intent | Tag | Automation |
|--------|-----|------------|
| `BILLING` | `billing` | Route Billing (also routes team/priority) |
| `ACCOUNT_ACCESS` | `login` | Tag Login |
| `REFUND` | `refund` | Tag Refund |
| `BUG_REPORT` or `TECHNICAL_ISSUE` | `bug` | Tag Bug |

### sla_policies / sla_timers

Policy: first_response_minutes, resolution_minutes, optional business_hours_id, applies_to JSONB.
Timer: type FIRST_RESPONSE|RESOLUTION, status RUNNING|PAUSED|COMPLETED|BREACHED.

### notifications / notification_preferences

In-app notifications per user. Preferences: per event_type in_app/email/enabled.
Users may hard-delete their own notifications only after `read_at` is set (`DELETE /notifications/{id}` → 204; unread → 409).

## Extended tables

### agent_availability

Added: `status` (ONLINE|AWAY|OFFLINE), `last_seen_at`, `active_conversation_count`. Backfilled from `is_online`.

### teams

Added: `last_assigned_user_id` for round-robin cursor.

## Enums

- `agent_status`: ONLINE, AWAY, OFFLINE
- `automation_execution_status`: RUNNING, COMPLETED, FAILED, SKIPPED
- `automation_step_type`: CONDITION, ACTION
- `sla_timer_type`: FIRST_RESPONSE, RESOLUTION
- `sla_timer_status`: RUNNING, PAUSED, COMPLETED, BREACHED

## Rollback

`alembic downgrade 0007_day6_automation` drops all Day 6 tables and columns.
