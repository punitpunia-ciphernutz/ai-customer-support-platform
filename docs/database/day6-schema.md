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

Unique `(organization_id, name)` on tags. M2M join tables for conversations and tickets.

### sla_policies / sla_timers

Policy: first_response_minutes, resolution_minutes, optional business_hours_id, applies_to JSONB.
Timer: type FIRST_RESPONSE|RESOLUTION, status RUNNING|PAUSED|COMPLETED|BREACHED.

### notifications / notification_preferences

In-app notifications per user. Preferences: per event_type in_app/email/enabled.

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
