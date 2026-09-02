# Day 4 Database Schema

Migration: `0005_day4_ai_reliability`

## New tables

### `prompts` / `prompt_versions`

Versioned LLM prompt templates. One active version per prompt name.

| Column | Type | Notes |
|--------|------|-------|
| `prompts.name` | string | Unique logical name (`support_agent_system`, `grounding_validator`) |
| `prompt_versions.version` | int | Incrementing version |
| `prompt_versions.template` | text | Jinja-style or plain template body |
| `prompt_versions.active` | bool | Only one active per prompt |

**Access:** `PromptService.get_active(name)` (Phase 11).

### `bot_configurations`

Per-channel overrides for bot mode and thresholds.

| Column | Type | Notes |
|--------|------|-------|
| `organization_id` + `channel` | unique | e.g. `WEB_CHAT`, `EMAIL` |
| `mode` | ai_mode enum | Overrides org default |

### `ai_evaluations` / `ai_evaluation_results`

Evaluation datasets and per-case run results.

| Column | Type | Notes |
|--------|------|-------|
| `ai_evaluations.cases` | JSONB | Array of evaluation case definitions |
| `ai_evaluation_results.passed` | bool | Expected vs actual match |

### `agent_availability`

Agent online status and schedule for routing.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | FK users | One row per agent |
| `is_online` | bool | Manual or heartbeat |
| `schedule` | JSONB | Weekly hours |

## Extended tables

### `conversations`

| Column | Type | Default |
|--------|------|---------|
| `ai_control_mode` | enum | `AI_CONTROL` |
| `conversation_summary` | text | nullable — rolling summary for token control |

### `tickets`

| Column | Type | Default |
|--------|------|---------|
| `customer_id` | FK customers | nullable |
| `source` | ticket_source enum | `AGENT_CREATED` |
| `title` | string | nullable |
| `description` | text | nullable — includes AI handoff package |

### `ai_runs`

| Column | Type | Purpose |
|--------|------|---------|
| `prompt_version` | string | e.g. `support_agent_system:v1` |
| `retrieval_score` | float | Aggregate rerank score |
| `grounding_score` | float | Post-generation validation |
| `confidence_components` | JSONB | Explainable breakdown |
| `decision` | string | `AI_RESOLVE`, `ESCALATE`, `SUGGEST_ONLY` |
| `language` / `sentiment` | string | Routing signals |
| `estimated_cost_usd` | float | Token cost estimate |
| `trace` | JSONB | Operational step trace |

### `ai_configs`

| Column | Type | Default |
|--------|------|---------|
| `min_relevance_score` | float | 0.35 |
| `require_knowledge` | bool | true |
| `escalate_if_unknown` | bool | true |
| `multilingual_enabled` | bool | true |
| `hybrid_keyword_weight` | float | 0.3 |
| `business_hours` | JSONB | Mon–Fri 09:00–18:00 UTC |
| `missed_chat_timeout_minutes` | int | 5 |

## Enums

- `ai_control_mode`: `AI_CONTROL`, `HUMAN_CONTROL`
- `ticket_source`: `AI_ESCALATION`, `MISSED_CHAT`, `AGENT_CREATED`, `HELP_CENTER`, `AUTOMATION`
- `conversation_status`: added `WAITING_FOR_AGENT`
- `ai_run_type`: added `EVALUATION`

## Relationships

```
Organization
├── ai_configs (1:1)
├── bot_configurations (1:N)
├── ai_evaluations (1:N)
└── agent_availability (1:N via users)

Conversation
├── ai_control_mode
├── conversation_summary
└── tickets (source, customer_id, title, description)

AIRun
├── prompt_version → prompts
└── ai_evaluation_results (optional FK)
```

## Important queries

- Active prompt: `SELECT * FROM prompt_versions WHERE prompt_id = ? AND active = true`
- Pending missed chats: conversations with `status = WAITING_FOR_AGENT` and `updated_at < now() - timeout`
- AI runs with low grounding: `SELECT * FROM ai_runs WHERE grounding_score < 0.5 AND type = 'AGENT'`
