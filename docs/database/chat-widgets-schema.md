# Chat Widgets — Schema Notes

Migration: `0011_chat_widgets` (revises `0010_response_policy`)

## Purpose

`chat_widgets` stores per-organization embeddable chat widget configuration. Widgets are a **delivery surface** for `ChannelType.WEB_CHAT` — they do not introduce a parallel message or AI pipeline.

## Table: `chat_widgets`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | Internal ID |
| `organization_id` | UUID FK → organizations | Indexed (`ix_chat_widgets_org`) |
| `public_id` | String(64) UNIQUE | Public Widget ID for embed (`wgt_…`) |
| `name` | String(255) | Dashboard label |
| `status` | enum `widget_status` | `DRAFT` \| `ACTIVE` \| `INACTIVE` |
| `allowed_domains` | JSONB | Host allowlist, e.g. `["example.com", "*.example.com"]` |
| `appearance` | JSONB | Colors, launcher position/text, border radius, z-index, logo |
| `welcome_message` | Text | Shown at first open |
| `offline_message` | Text nullable | Shown when inactive |
| `require_email` | bool | Pre-chat form |
| `require_name` | bool | Pre-chat form |
| `ai_settings` | JSONB nullable | Reserved; v1 inherits WEB_CHAT bot config |
| `created_at` / `updated_at` | timestamptz | |

Indexes:

- `uq_chat_widgets_public_id` on `public_id`
- `ix_chat_widgets_org` on `organization_id`

## Column: `conversations.widget_id`

| Column | Type | Notes |
|--------|------|--------|
| `widget_id` | UUID FK → chat_widgets NULL | Set for embed-originated chats; null for legacy `/chat` |

Index: `ix_conversations_widget_id`.

## Customer visitor identity

Anonymous visitors use:

```
external_id = widget:{public_id}:vid:{visitor_uuid}
```

Partial unique index `uq_customers_org_external_id` on `(organization_id, external_id)` where `external_id IS NOT NULL`.

## Access patterns

| Who | How |
|-----|-----|
| Agents | `/api/v1/widgets` CRUD (settings.read / settings.write) |
| Embed | `/api/v1/public/widgets/{public_id}/…` — domain allowlist + visitor JWT |
| AI / tickets | Unchanged — still via `ConversationService` + Celery |

## Status behavior

| Status | Public config | Messaging |
|--------|---------------|-----------|
| `DRAFT` | 404 (OK with valid Settings preview token) | Rejected (unless preview token for session APIs) |
| `ACTIVE` | OK (domain checked; ≥1 domain required) | OK if WEB_CHAT enabled |
| `INACTIVE` | OK (offline UX) | 403 |

## Settings Live Preview

Admin Settings loads `widget-frame.html?…&preview=true&preview_token=…`. With `preview=true` the embed:

- Does **not** read/write visitor `localStorage` or load real conversation messages
- Renders a static sample thread (welcome + sample user/agent bubbles)
- Accepts `postMessage` `WIDGET_PREVIEW_UPDATE` for unsaved appearance/welcome drafts
- Does not persist messages to the database

## Relations

```
Organization 1—* ChatWidget
ChatWidget 1—* Conversation (nullable FK)
Customer ← visitor JWT sub
```

## Rollback

Migration is additive. Downgrade drops `conversations.widget_id`, the partial customer index, and `chat_widgets`.
