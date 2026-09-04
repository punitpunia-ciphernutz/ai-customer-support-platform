# Response Policy — Schema Notes

Migration: `0010_response_policy` (revises `0009_ai_config_llm_model`)

## `ai_configs` columns added

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `response_policy_enabled` | bool | true | Master kill switch |
| `soft_reply_greetings` | bool | true | Soft-reply GREETING / IDENTITY / SMALL_TALK |
| `ood_soft_refuse` | bool | true | Soft-refuse true OOD and SUPPORT+no-KB |
| `ood_escalates` | bool | false | Force ticket on OOD / no-KB |
| `safe_reply_min_kind_confidence` | float | 0.55 | Min kind confidence for safe soft replies |
| `assistant_scope_summary` | string(1000) | help-center scope text | Soft templates |
| `assistant_display_name` | string(128) | Support Assistant | Identity soft replies |

## Runtime notes

- `MessageKind` and `PolicyAction` live in application schemas (not DB enums).
- `AgentDecision.SOFT_REPLY` allows Autopilot/DRAFT_ONLY to send without KB grounding.
- Missing KB never rewrites `message_kind` to `OUT_OF_DOMAIN`; soft refuse uses `SoftRefuseKind.INSUFFICIENT_KNOWLEDGE`.
