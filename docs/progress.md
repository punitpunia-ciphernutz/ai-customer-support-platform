# Progress — AI Customer Support Platform

Last updated: 2026-09-01

## Status summary

**Day 1, Day 2, Day 3, and Day 4 are complete (re-audited 2026-09-01).** The platform now has production-control AI: hybrid retrieval, grounding validation, explainable confidence, bot modes with takeover/kill switch, AI handoff packages, run tracing, evaluation suite (25 cases), channel overrides, Celery Beat missed-chat processing, and updated agent UI.

**Frontend UI:** Settings uses spec mode names (Knowledge Base / Suggest Reply / Autopilot), per-channel override table, evaluation runner, run trace/grounding/token detail. Inbox has takeover/return-to-AI, suggestion panel with Use/Edit/Regenerate/Ignore, and grounding warnings.

LLM: **Google Gemini** when `GEMINI_API_KEY` is set; otherwise **Echo/heuristic** + offline lexical embeddings. Unset `GEMINI_API_KEY` for fully offline tests (avoids embedding quota errors).

## Day 4 — Completed

| Phase | Work |
|-------|------|
| 1 | Migration `0005_day4_ai_reliability`: prompts, bot configs, evaluation tables, extended `AIRun`/`AIConfig`, `Conversation.ai_control_mode`, ticket source/handoff fields |
| 2 | ContextBuilder v2 + `ConversationSummarizer` + graph `load_context` |
| 3 | Hybrid retrieval (semantic + keyword), `RelevanceGate`, conditional knowledge branch |
| 4 | `GroundingValidator` + graph `grounding_check` node |
| 5 | `confidence_service.py` — explainable `ConfidenceBreakdown` persisted on runs |
| 6 | LangGraph v2 (`support-agent-v2`): prepare_query → retrieve → gate → generate → ground → confidence → decision; step tracing |
| 7 | Bot modes (Knowledge Base / Suggest / Autopilot), takeover/return-to-AI APIs, kill switch + human control guards, **`RuntimeAIConfig` channel overrides** |
| 8 | `AvailabilityService`, `MissedChatService`, `WAITING_FOR_AGENT`, `/agents/availability`, **Celery Beat `process_missed_chats`** |
| 9 | `EscalationService` handoff package, ticket sources, `/conversations/{id}/ticket` |
| 10 | Run trace JSON, cost estimator, extended run detail API |
| 11 | `PromptService` + DB-seeded prompt versions |
| 12 | `EvaluationService` — 25 cases, `GET/POST /ai/evaluations` |
| 13 | Language from classify node, sentiment normalization, routing priority |
| 14 | Settings + Inbox UI (suggestions, takeover, diagnostics) |

## Day 4 tests

`backend/tests/test_day4_*.py` — **16 tests** (models, context, retrieval, grounding, takeover, evaluation suite).

Run: `docker compose exec backend pytest -q tests/test_day4_phase1_models.py tests/test_day4_phase2_context.py tests/test_day4_phase3_retrieval.py tests/test_day4_acceptance.py`

## Day 3 — Completed (prior)

| Phase | Work |
|-------|------|
| 1–14 | Working AI agent, Celery async, escalation, basic UI — see `docs/day3-implementation-plan.md` |

## Documentation

- Day 4 plan: [`docs/day4-implementation-plan.md`](day4-implementation-plan.md)
- Day 4 schema: [`docs/database/day4-schema.md`](database/day4-schema.md)
- Run guide: [`docs/run-guide.md`](run-guide.md)

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Notes

- **Graph version:** `support-agent-v2`
- **Evaluation:** Settings → Run evaluation suite, or `POST /api/v1/ai/evaluations/run`
- **Takeover:** Inbox thread → Takeover / Return to AI
- **Suggest mode:** AI suggestions appear as internal messages; Use Reply in inbox composer
- Integration tests that hit Gemini embeddings may fail on quota — use offline Echo for CI
