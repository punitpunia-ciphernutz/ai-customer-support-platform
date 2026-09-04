# Response Policy & AI Message Understanding — Implementation Plan

**Goal:** Add LLM-driven message understanding (`MessageKind`) and a deterministic **Response Policy** so Autopilot can soft-reply to greetings/chitchat and soft-refuse out-of-domain questions, while reusing the existing classification, LangGraph, KB retrieval, grounding, confidence, escalation, and ticket stack.

**Rule:** Extend; do not fork a second bot. Do not replace `evaluate_escalation` or `_apply_side_effects` for the support path.

**Status:** Implemented (Phases 1–5). Approved decisions locked in code/defaults.

**Approved decisions:**
- `response_policy_enabled` default = **true** (kill switch preserved)
- DRAFT_ONLY may send safe soft replies for greetings/identity
- UNCLEAR: real support → continue KB; otherwise short clarification
- No KB ≠ automatic OUT_OF_DOMAIN — keep `SUPPORT_REQUEST + no KB` separate from true OOD

**Depends on:** Days 1–6 (conversations, knowledge, support agent, AIConfig/modes, escalation tickets, Celery).

---

## Problem (today)

With defaults (`require_knowledge=True`, high confidence thresholds, seed `restricted_intents=["OTHER"]`):

- `"Hello"` / `"Who are you?"` / OOD questions → retrieval fails → **ESCALATE** → ticket notice, no friendly reply.
- Autopilot only **sends** when `decision=AI_RESOLVE` **and** `grounded=True` (`AIService._apply_side_effects`).
- There is no conversational “message kind” — only support `IntentLabel`.

FAQ Autopilot (password reset, etc.) and human-request escalation already work and must stay unchanged.

---

## Current workflow → Target workflow

### Current (support agent)

```
load_context → classify_intent → detect_language → prepare_query
  → retrieve_knowledge → evaluate_retrieved_context
       ├─ no KB → skip generate → confidence → evaluate_escalation → ESCALATE
       └─ KB OK → generate → grounding → confidence → evaluate_escalation
            → AI_RESOLVE | ESCALATE | SUGGEST_ONLY
  → finalize (if resolve)
→ AIService._apply_side_effects (send if grounded resolve; else ticket)
```

**Entry points (unchanged):** Celery `process_ai_message` → `AIService.process_customer_message` / `run_support_agent`; AI Test Console `run_test` (no side effects).

### Target

```
load_context → classify_intent (+ MessageKind)
  → apply_response_policy                    ← NEW
       ├─ SAFE_REPLY / SOFT_REFUSE
       │     → soft draft (templates) → confidence → SOFT_REPLY → finalize
       ├─ ESCALATE_NOW (human / angry)
       │     → confidence → evaluate_escalation (existing)
       └─ CONTINUE_SUPPORT
             → detect_language → prepare_query → retrieve → …
             → if no KB: Response Policy OOD branch (soft refuse vs escalate)
             → else: generate → ground → evaluate_escalation (existing)
→ _apply_side_effects
     SOFT_REPLY + Autopilot → _save_ai_reply (no grounding required)
     SOFT_REPLY + Suggest → _save_suggestion only
     AI_RESOLVE / ESCALATE → existing rules
```

**Where it fits:** After classification (needs kind + human flags), before/around retrieval. Support FAQ path from retrieve onward stays Day 4 behavior.

---

## AI-driven MessageKind (classification schema)

Keep **`IntentLabel`** for support routing (billing, access, …). Add orthogonal **`MessageKind`** via structured LLM output — **not** a large static greeting/question list.

| MessageKind | Role |
|-------------|------|
| `GREETING` | Hello / hi with little or no task |
| `IDENTITY` | Who/what is the assistant |
| `SMALL_TALK` | Thanks / filler without a support ask |
| `SUPPORT_REQUEST` | Real help need (may include “Hi, how do I…”) |
| `HUMAN_REQUEST` | Ask for live agent |
| `OUT_OF_DOMAIN` | Outside product support scope |
| `UNCLEAR` | Too vague; prefer clarify or continue support |

### Extend `AIClassification`

```
intent, language, sentiment, confidence, requires_human   # existing
message_kind: MessageKind                                 # new
message_kind_confidence: float                            # new
```

Prompt (Gemini): define kinds; prefer `SUPPORT_REQUEST` when a real task is present; prefer `HUMAN_REQUEST` when both greeting and human ask appear.

Echo: **minimal** offline heuristics for tests only (reuse `detect_human_request`; do not ship a production phrase dictionary).

### State / decision additions

- `SupportAgentState`: `message_kind`, `message_kind_confidence`, `policy_action`, `policy_allows_ungrounded_send`
- `AgentDecision`: add **`SOFT_REPLY`** (explicit ungrounded-safe send; do not fake `grounded=True`)
- Optional: `PolicyAction` = `SAFE_REPLY` | `SOFT_REFUSE` | `CONTINUE_SUPPORT` | `ESCALATE` | `CLARIFY`

---

## Response Policy logic

**New module:** `backend/app/modules/ai/application/response_policy.py`

Deterministic: `(message_kind, mode, knowledge_available, human_requested, sentiment, config) → policy_action + decision hint`.

| Situation | Autopilot | Suggest |
|-----------|-----------|---------|
| Greeting / identity / small talk | Soft reply, **no ticket** | Internal suggestion only |
| Support + KB grounded | Existing `AI_RESOLVE` | Existing suggest |
| OOD / no relevant KB | Soft refuse (default); ticket only if `ood_escalates` | Suggestion |
| Human / angry / hard restricted | Existing escalate + ticket | Existing |

**Config knobs (additive on `AIConfig`):**

- `response_policy_enabled` (kill switch → legacy path)
- `soft_reply_greetings`, `ood_soft_refuse`, `ood_escalates`
- `safe_reply_min_kind_confidence`
- `assistant_scope_summary` (text for soft templates)

**Soft copy:** Short templates (welcome / identity / “I only help with {scope}”) — no invented product facts. Optional light LLM rewrite later.

**Interaction with `evaluate_escalation`:** Soft paths must **not** escalate solely because `intent=OTHER`, low retrieval, or seed `restricted_intents=["OTHER"]`. Still honor human request and angry sentiment. Support path still calls `evaluate_escalation` unchanged.

---

## Data flow

```
Customer message (WEB_CHAT / EMAIL)
  → AI enabled? / HUMAN_CONTROL?          # unchanged
  → ContextBuilder + timed_support_agent
  → classify → MessageKind + IntentLabel
  → Response Policy → soft branch OR full KB pipeline
  → decision (SOFT_REPLY | AI_RESOLVE | ESCALATE | SUGGEST_ONLY)
  → if persist_side_effects: _apply_side_effects
       → Message (AI / suggestion) and/or EscalationService ticket
  → AIRun trace stores kind + policy_action + decision
  → /ai/test returns same fields (no persist)
```

---

## Files / components to change

| Area | Path |
|------|------|
| Schemas | `domain/schemas.py` |
| Models / migration | `domain/models.py`, new Alembic migration, `docs/database/` note |
| Policy | **New** `application/response_policy.py` (+ safe-reply templates) |
| Runtime / seed | `runtime_config.py`, `ai_config_service.py`, `scripts/seed.py` |
| Classify | `graphs/classification.py`, `infrastructure/llm/providers.py`, prompts |
| Graph | `graphs/support_agent.py` (+ `_fallback_support_agent` parity) |
| Escalation / confidence | Soft-path exemptions only in `escalation.py` / `confidence_service.py` |
| Side effects / API | `ai_service.py`, `api/routes.py` |
| UI | `SettingsPage.tsx` (knobs + test console fields) |
| Tests / manual | New `test_response_policy.py`; extend day3–5 suites; `manual-test-scenarios.md` |

---

## Fallback behavior

| Case | Behavior |
|------|----------|
| `response_policy_enabled=false` | Exact legacy graph + side effects |
| Missing / low `message_kind_confidence` | Do not SAFE_REPLY; `CONTINUE_SUPPORT` (conservative) |
| Classification failure | Treat as `SUPPORT_REQUEST` → KB path |
| LangGraph unavailable | Fallback agent must mirror policy branches |
| Suggest + soft | Suggestion only — never customer auto-send |
| Soft refuse then “talk to human” | Next turn → existing human escalate |
| Echo offline | Minimal kind heuristics for pinned tests |

---

## Implementation phases

1. **Schemas + config** — enums, AIConfig columns, runtime merge, seed (behavior inert or flag off)
2. **Classification** — emit `message_kind` (optional shadow: store, ignore policy)
3. **Policy + graph + side effects** — soft reply/refuse, `SOFT_REPLY` send path, kill switch
4. **API + Settings** — config knobs, `/ai/test` shows kind + policy + decision
5. **Harden** — tests, eval cases, short audit doc after ship

---

## Testing / regression

**Add**

- Greeting → soft reply, no ticket (Autopilot)
- Identity → soft reply, no ticket
- OOD / no KB → soft refuse, no ticket (default)
- Same OOD + `ood_escalates` → ticket
- Password FAQ → grounded `AI_RESOLVE` (unchanged)
- Human request → escalate + ticket
- Suggest + greeting → suggestion only
- Policy off + greeting → legacy escalate

**Must stay green:** `test_day3_agent`, `test_day4_modes`, `test_day5_email_*`, HUMAN_CONTROL / takeover tests.

---

## Backward compatibility — what must not break

- Grounded FAQ Autopilot customer sends
- Suggest never customer-auto-sends
- Human / angry / restricted hard escalations and tickets
- `IntentLabel` values, Celery entry, `TicketSource.AI_ESCALATION`, Day 6 automations
- Additive DB/API only; no historical migration edits
- Kill switch restores pre-feature behavior for greetings/OOD

---

## Definition of Done

- [ ] LLM classifies `MessageKind` without a large static list
- [ ] Autopilot soft-replies greetings/identity; soft-refuses OOD by default
- [ ] FAQ Autopilot, Suggest, human escalate, email paths unchanged when applicable
- [ ] `response_policy_enabled=false` restores legacy
- [ ] Tests + manual scenarios updated; DB/config docs updated

## Open decisions (before Phase 3)

1. Ship with `response_policy_enabled` default `true` or `false`?
2. Knowledge Base (`DRAFT_ONLY`) mode: send soft replies or stay silence-on-ungrounded?
3. `UNCLEAR`: one clarify soft reply vs always continue support retrieval?

**Recommendation:** default policy **on**; soft-send in DRAFT_ONLY for greetings; `UNCLEAR` with substance → continue support, else short clarify.
