# Day 4 Implementation Plan — AI Reliability, Human Handoff & Production Control

**Goal:** Make the Day 3 AI flow reliable enough for serious testing: grounded answers, explainable confidence, deterministic bot modes, human safeguards, operational visibility, and an evaluation baseline—without adding new channels or integrations.

**Rule:** Extend Day 3 architecture (Celery async, LangGraph support agent, existing modules). No tool calling. No email/omnichannel (Day 5).

**Depends on:** Day 1 (conversations, messages, tickets, Celery, WebSocket) + Day 2 (knowledge, vector retrieval, `AIRun`) + Day 3 (support agent graph, `ContextBuilder`, reranker, confidence, escalation, `AIConfig`, basic UI).

**Key existing hooks (extend, don't fork):**

| Area | Path |
|------|------|
| AI orchestration | `backend/app/modules/ai/application/ai_service.py` |
| Context (basic) | `backend/app/modules/ai/application/context_builder.py` |
| Confidence (basic) | `backend/app/modules/ai/application/confidence.py` |
| Escalation | `backend/app/modules/ai/application/escalation.py`, `escalation_service.py` |
| Support graph | `backend/app/modules/ai/graphs/support_agent.py` |
| Reranker | `backend/app/modules/ai/infrastructure/reranker.py` |
| Config | `backend/app/modules/ai/domain/models.py` (`AIConfig`, `AIRun`) |
| Prompts (inline v1) | `backend/app/modules/ai/prompts/support_agent_v1.py` |
| APIs | `backend/app/modules/ai/api/routes.py` |
| Celery worker | `backend/app/workers/tasks.py` |
| Agent inbox UI | `frontend/src/features/inbox/InboxPage.tsx` |
| Settings UI | `frontend/src/features/settings/SettingsPage.tsx` |

**Mode naming alignment (Day 3 → Day 4 spec):**

| Day 3 enum | Day 4 spec | Behavior |
|------------|------------|----------|
| `DRAFT_ONLY` | `KNOWLEDGE_BASE` | AI answers only when knowledge sufficient; else escalate |
| `SUGGEST` | `SUGGEST_REPLY` | AI generates suggestion; never sends customer message |
| `AUTO_REPLY` | `AUTOPILOT` | AI sends when confidence + grounding + policy pass |

---

## Target runtime flow

```
Customer Message
  → Conversation Controller (AI enabled? control mode? availability?)
  → Bot Mode (Knowledge Base / Suggest Reply / Autopilot)
  → LangGraph Support Agent
      ├── Context Builder (customer + memory strategy)
      └── Hybrid Retrieval → Rerank → Relevance threshold
  → Generate Answer
  → Grounding Validator (separate check)
  → Confidence Engine (component scores, explainable)
  → Decision
      ├── Resolve → AI reply (mode permitting)
      └── Escalate → Ticket + AI Handoff Package
  → AI Run Trace + token/cost metadata
```

---

## Recommended order (critical path)

```
1. DB migration (Prompt, PromptVersion, AIRun extensions, Conversation.ai_control_mode, BotConfiguration, evaluation tables)
2. Context Builder v2 + conversation memory (summary + recent messages)
3. Hybrid retrieval + relevance threshold gate
4. Grounding validator (post-generation, blocks Autopilot on failure)
5. Confidence engine v2 (component scores + explainability payload)
6. LangGraph graph update (new nodes + conditional branches)
7. Bot modes + agent takeover + return-to-AI + kill switch checks in worker
8. Working hours / availability + missed chat → ticket routing
9. Escalation service v2 (handoff package, ticket sources, routing)
10. AI run tracing + cost/token tracking + prompt version on runs
11. Prompt versioning service + DB-backed templates
12. Evaluation framework + 20–30 test cases + run/report API
13. Multilingual + sentiment (routing signals)
14. Frontend: AI settings, suggestion UX, takeover controls, run diagnostics
15. Acceptance tests + Definition of Done checklist
```

---

## Phase 1 — Database & domain models

**Unlocks:** tracing, versioning, control modes, evaluation, availability config

### New / extended tables

| Entity | Purpose |
|--------|---------|
| `Prompt` | Named prompt family (`support_agent_system`, `grounding_validator`, etc.) |
| `PromptVersion` | `name`, `version`, `template`, `model`, `configuration`, `active`, `created_at` |
| `BotConfiguration` | Org-level + per-channel overrides (mode, thresholds, multilingual, require_knowledge) |
| `AIEvaluation` | Evaluation dataset definition (name, version, case count) |
| `AIEvaluationResult` | Per-run/per-case results (expected vs actual, scores) |
| `Conversation.ai_control_mode` | `AI_CONTROL` \| `HUMAN_CONTROL` |
| `AIRun` extensions | `prompt_version`, `grounding_score`, `confidence_components` (JSONB), `decision`, `retrieval_score`, `estimated_cost_usd`, `trace` (JSONB steps), `language`, `sentiment` |
| `AgentAvailability` (or extend existing agent model) | Online/offline, schedule JSON, timezone |
| `OrganizationSettings` extensions | `business_hours`, `missed_chat_timeout_minutes`, `ai_kill_switch` (may live on `AIConfig.enabled`) |

### Alembic

- Migration: `0005_day4_ai_reliability.py`
- Seed: default prompts v1, demo evaluation cases stub, default business hours

### Tasks

- [x] Models in `backend/app/modules/ai/domain/models.py` (+ availability if new module)
- [x] Pydantic schemas: `ConfidenceBreakdown`, `GroundingResult`, `AIHandoffPackage`, `AIRunTraceStep`, `EvaluationCase`, `EvaluationReport`
- [x] Map `AIMode` labels in API responses to Day 4 names where useful for UI
- [x] Document schema in `docs/database/` (tables, relationships, query patterns)

---

## Phase 2 — Context builder & conversation memory

**Path:** `backend/app/modules/ai/application/context_service.py` (or extend `context_builder.py`)

### ContextBuilder v2 sections

```
ContextBuilder
├── Customer Context (name, company, metadata)
├── Conversation History (last N messages, labeled turns)
├── Conversation Summary (persistent, updated on threshold)
├── Current Message
├── Previous AI Responses (last 1–3 for continuity)
├── Ticket Context (open ticket linked to conversation, if any)
└── Relevant Metadata (channel, status, control mode, language)
```

### Memory strategy (token cost control)

- **Recent messages:** last 10 (configurable, token-budget cap)
- **Summary:** generate/update when message count exceeds threshold (e.g. every 20 messages or on escalation)
- **Do not** dump full conversation into every LLM call
- Store summary on `Conversation.metadata_` or dedicated `conversation_summaries` column/table

### Tasks

- [x] `ContextBuilder.build()` returns structured sections for prompts and graph state
- [x] `ConversationSummarizer.summarize_if_needed(conversation_id)` — async, idempotent
- [x] Unit test: multi-turn "I tried that but it still doesn't work" uses prior AI reply + history
- [x] Wire into graph `build_context` node (replace stub `load_context_node`)

---

## Phase 3 — Hybrid knowledge retrieval & relevance threshold

**Paths:** `backend/app/modules/ai/infrastructure/retrieval/`, extend `reranker.py`

### Day 4 retrieval pipeline

```
Query Preparation (intent-enriched query, language hint)
  → Hybrid Retrieval
      ├── Semantic (existing PgVectorRetriever)
      └── Keyword (BM25 / PostgreSQL full-text on chunks — lightweight)
  → Reranking (existing LLM or blend scores)
  → Relevance Threshold Gate
      ├── score >= min_relevance → pass top context to generation
      └── score < min_relevance → "No sufficiently relevant knowledge found" → escalate path
```

### Config

- `AIConfig` / `BotConfiguration`: `min_relevance_score`, `require_knowledge` (bool), `hybrid_keyword_weight`

### Tasks

- [x] `QueryPreparer.prepare(state) -> str`
- [x] `HybridRetriever.search()` combining vector + keyword hits with dedup
- [x] `RelevanceGate.evaluate(docs, threshold) -> pass | fail + reason`
- [x] Graph nodes: `prepare_query`, `retrieve_knowledge`, `rerank`, `knowledge_available?` conditional
- [x] Unit tests: empty KB, low-score query, high-score FAQ

---

## Phase 4 — Grounding validation

**Path:** `backend/app/modules/ai/application/grounding_validator.py` (new)

### Post-generation check (separate from generation model self-report)

```
Retrieved Knowledge + Generated Answer
  → GroundingValidator (LLM structured output or dedicated small prompt)
  → { grounded: bool, score: 0.0–1.0, unsupported_claims?: [] }
```

### Policy

| Mode | `grounded = false` |
|------|---------------------|
| **Autopilot** | Do **not** send response → escalate |
| **Knowledge Base** | Do **not** send → escalate |
| **Suggest Reply** | Show suggestion with warning badge; agent decides |

### Tasks

- [x] `GroundingValidator.validate(answer, sources) -> GroundingResult`
- [x] DB-backed prompt version for grounding check
- [x] Graph node `grounding_check` after `generate_answer`
- [x] Store `grounding_score` on `AIRun` and in confidence breakdown
- [x] Tests: hallucinated answer with no sources → `grounded=false`

---

## Phase 5 — Explainable confidence engine

**Path:** `backend/app/modules/ai/application/confidence_service.py` (extend `confidence.py`)

### Component scores (all persisted)

| Component | Source |
|-----------|--------|
| Intent confidence | classify node |
| Retrieval relevance | reranker aggregate |
| Grounding score | grounding validator |
| Context completeness | history + customer fields present |
| Response validation | non-empty, policy checks |
| Policy result | mode, thresholds, human request, kill switch |

```
Final confidence = weighted blend (weights in AIConfig)
Decision = RESOLVE | ESCALATE | SUGGEST_ONLY (mode-dependent)
```

### Explainability (internal only)

```json
{
  "final": 0.72,
  "components": {
    "intent": 0.94,
    "retrieval": 0.61,
    "grounding": 0.78,
    "context": 0.85,
    "policy": 1.0
  },
  "decision": "ESCALATE",
  "reasons": ["Knowledge relevance below threshold"]
}
```

- Expose in agent inbox / run detail API — **never** in customer-facing messages

### Tasks

- [x] Refactor `calculate_support_confidence` → return `ConfidenceBreakdown`
- [x] Persist full breakdown on `AIRun.confidence_components`
- [x] Graph node `calculate_confidence` → `decision` with explicit reasons array
- [x] Unit tests with fixed inputs for each escalation path

---

## Phase 6 — LangGraph support agent update

**Path:** `backend/app/modules/ai/graphs/support_agent.py`

### Target graph

```
START
  → load_conversation
  → load_customer
  → build_context
  → detect_language          (new)
  → classify_intent          (+ sentiment)
  → prepare_query
  → retrieve_knowledge       (hybrid)
  → rerank
  → knowledge_available? ──NO──→ prepare_escalation (insufficient knowledge)
  │ YES
  → generate_answer
  → grounding_check
  → calculate_confidence
  → decision
      ├─ RESOLVE → finalize_response → END
      └─ ESCALATE → prepare_escalation_summary → END
```

- Record per-step trace (status, duration_ms, metadata) in graph runner — no chain-of-thought
- Attach `prompt_version` from active DB prompt to each run
- `graph_version`: bump to `support-agent-v2`

### Tasks

- [x] Implement conditional edge after retrieval
- [x] Wire grounding node before confidence
- [x] `timed_*` wrapper for each step → append to `AIRun.trace`
- [x] Integration test via `POST /api/v1/ai/test` for resolve + escalate paths

---

## Phase 7 — Bot modes, agent takeover & AI kill switch

### 7a — Deterministic bot modes

**Path:** `backend/app/modules/ai/application/agent_service.py` (or extend `ai_service.py`)

| Mode | Send to customer? | On low confidence / no knowledge / not grounded |
|------|-------------------|--------------------------------------------------|
| Knowledge Base | Yes, if knowledge + grounding pass | Escalate / ticket |
| Suggest Reply | **Never** | Store suggestion for agent; emit `suggestion.generated` event |
| Autopilot | Yes, if confidence ≥ threshold + grounded | Escalate / ticket |

- Channel override via `BotConfiguration` (e.g. Web Chat = Autopilot, Email = Suggest Reply — email channel stub OK for config only)

### 7b — Agent takeover safeguard

- `Conversation.ai_control_mode`: `AI_CONTROL` (default) | `HUMAN_CONTROL`
- On takeover: set `HUMAN_CONTROL`; worker **must** skip customer-facing AI sends
- `POST /api/v1/conversations/{id}/takeover` — agent auth
- `POST /api/v1/conversations/{id}/return-to-ai` — restores `AI_CONTROL`
- Suggest Reply still allowed under human control (agent tool, not auto-send)

### 7c — AI kill switch

- `AIConfig.enabled` = global org kill switch
- Admin UI toggle: **AI Support [ ON | OFF ]**
- Celery worker checks **current** config before sending any AI reply (not stale job snapshot)
- When OFF: route to human availability flow or missed-chat ticket path

### Tasks

- [x] Mode enforcement in `AIService.process_customer_message()` and `_save_ai_reply`
- [x] Takeover / return-to-AI endpoints on conversation router
- [x] Worker pre-send guard: `enabled`, `ai_control_mode`, mode
- [x] Frontend: takeover button + "Return to AI" in inbox thread header
- [x] Tests: Suggest mode never creates `sender_type=AI` customer messages; takeover blocks Autopilot

---

## Phase 8 — Working hours, availability & missed chat routing

### Availability foundation

```
Business Hours (org schedule)
Agent Availability (online/offline per agent)
AI Availability (follows AIConfig.enabled + optional schedule)
```

### Routing logic (conversation controller)

```
Incoming message
  → AI enabled?
      YES → run AI pipeline (respect control mode)
      NO  → agents available?
          YES → queue for agent / notify
          NO  → conversation waiting → timeout → create ticket
```

### Missed chat → ticket

- Config: `missed_chat_timeout_minutes` (org setting)
- Background task or Celery beat: scan waiting conversations past timeout
- Create ticket with source `MISSED_CHAT`, assign team, notify customer template

### Outside business hours

- AI may still resolve if Autopilot + confident
- If human required → create ticket + customer message: *"Support team will respond..."*

### Tasks

- [x] `AvailabilityService.is_agent_available(org_id)`, `is_within_business_hours(org_id)`
- [x] `GET/PATCH /api/v1/agents/availability`
- [x] `MissedChatService.process_timeouts()` — Celery periodic task wired via `beat` service
- [x] Conversation status/state for `WAITING_FOR_AGENT`
- [x] Tests: AI OFF + agents OFFLINE → timeout → ticket (service layer)

---

## Phase 9 — Ticket routing, escalation & AI handoff package

**Path:** extend `backend/app/modules/ai/application/escalation_service.py`

### Reusable ticket decision service

```
Conversation → TicketDecisionService → TicketService
```

**Ticket sources:** `AI_ESCALATION`, `MISSED_CHAT`, `AGENT_CREATED`, `HELP_CENTER`, `AUTOMATION`

**Required ticket fields:** `source`, `conversation_id`, `customer_id`, `team`, `assignee`, `priority`

### AI handoff package (top of ticket / internal note)

```
Customer + company
Issue summary
Intent + AI confidence (final + breakdown summary)
Knowledge searched (doc titles)
What AI tried
Why escalated
Recommended action
```

- Render as structured internal note (`sender_type=SYSTEM` or ticket `description` prefix)
- Customer sees short handoff line only if policy allows

### Sentiment → routing

- `ANGRY` / `NEGATIVE` → bump `priority` to `HIGH`; optional manager team from config

### Tasks

- [x] `EscalationService.build_handoff_package(state, ai_run) -> AIHandoffPackage`
- [x] `TicketService.create_from_escalation(..., source=AI_ESCALATION | MISSED_CHAT)`
- [x] `POST /api/v1/conversations/{id}/ticket` (agent-initiated)
- [x] Intent → team map (existing `AIConfig.intent_team_map`) + sentiment overrides
- [x] Tests: unknown question → ticket with handoff fields populated

---

## Phase 10 — AI run tracing & cost/token tracking

### Per-run trace (operational, not CoT)

Each step: `name`, `status`, `duration_ms`, `input_summary`, `output_summary`, `error`

Example steps: Message Received → Context Loaded → Intent → Retrieval → Rerank → Generation → Grounding → Confidence → Decision → Response Sent

### Cost tracking

| Field | Source |
|-------|--------|
| Model | LLM provider response |
| Input / output / total tokens | provider usage |
| Estimated cost | model pricing table in config |
| Latency | wall clock per run |

- Store on `AIRun`; aggregate later for cost-per-resolution analytics (query only, no dashboard required Day 4)

### Tasks

- [x] Extend `LLMProvider` to return token usage consistently
- [x] `CostEstimator.estimate(model, tokens) -> Decimal`
- [x] Persist `trace`, `token_usage`, `estimated_cost_usd`, `latency_ms` on completion
- [x] `GET /api/v1/ai/runs/{id}` returns full trace + cost breakdown
- [ ] List endpoint filters by date, decision, mode (deferred — basic list works)

---

## Phase 11 — Prompt versioning

**Path:** `backend/app/modules/ai/prompts/` + `PromptService`

### DB-backed prompts

```
Prompt (logical name)
  └── PromptVersion (v1, v2, v3 — one active per prompt name)
```

- Migrate inline `support_agent_v1.py` templates to DB seed; keep file renderers as fallback/dev
- Every `AIRun` records `prompt_version` (e.g. `support_agent_system:v2`)

### Tasks

- [x] `PromptService.get_active(name) -> PromptVersion`
- [x] Admin API or seed script to activate version
- [x] Graph loads templates from `PromptService` at runtime (DB template with file fallback)
- [x] Test: two versions produce different `prompt_version` on runs

---

## Phase 12 — AI evaluation framework & test suite

**Path:** `backend/app/modules/ai/application/evaluation_service.py`

### Evaluation case schema

```yaml
input: "How do I reset my password?"
expected_intent: ACCOUNT_ACCESS
expected_behavior: ANSWER | ESCALATE | SUGGEST
expected_answer_contains: ["password", "reset"]
expected_escalation: false
knowledge_documents: ["Password Reset Guide"]
category: FAQ | Billing | Account | Technical | Unknown | Ambiguous | Angry | HumanRequest | Multilingual | OutOfScope
```

### Automated suite (20–30 cases)

Categories per spec: FAQ, Billing, Account, Technical, Unknown, Ambiguous, Angry customer, Human request, Multilingual, Out-of-scope

### Run flow

```
Evaluation Dataset → AI Agent (test mode, no side effects) → Compare → EvaluationReport
```

Metrics: intent accuracy, grounding rate, escalation accuracy, answer quality (contains / LLM judge optional)

### APIs

| Method | Path |
|--------|------|
| `GET` | `/api/v1/ai/evaluations` |
| `POST` | `/api/v1/ai/evaluations/run` |
| `POST` | `/api/v1/ai/test` | (existing — reuse for single case) |

### Tasks

- [x] Seed 20–30 cases in migration or JSON fixture under `backend/tests/fixtures/ai_eval/`
- [x] `EvaluationService.run_suite(org_id) -> EvaluationReport`
- [x] Persist `AIEvaluation` + `AIEvaluationResult` rows
- [x] CLI or pytest entry: `pytest tests/test_day4_acceptance.py`
- [x] Document baseline targets in plan footer after first run

---

## Phase 13 — Multilingual & sentiment detection

### Language detection

- Detect on incoming message (fast path: LLM classify node or lightweight library)
- Respond in detected language (generation prompt instruction + validation)
- KB may remain English; model translates context as needed

### Sentiment classifier

Labels: `POSITIVE`, `NEUTRAL`, `NEGATIVE`, `ANGRY`

- Primary use: routing (priority, team) — **not** personality changes
- Extend existing classification output (Day 3 stub in `LLMProvider`)

### Tasks

- [x] `detect_language` graph node → `state.language`
- [x] Generation prompt: reply in `state.language`
- [x] Sentiment on `AIRun` + handoff package
- [x] Tests: Spanish password question → Spanish response; angry message → HIGH priority ticket

---

## Phase 14 — Frontend: AI settings, suggestion UX & diagnostics

### AI Settings UI (`SettingsPage.tsx`)

- AI Support ON/OFF (kill switch)
- Default mode radio: Knowledge Base / Suggest Reply / Autopilot
- Confidence threshold slider
- Require knowledge toggle
- Escalate if unknown toggle
- Multilingual toggle
- Per-channel mode overrides table

### Suggest Reply UX (`InboxPage.tsx`)

```
┌ AI Suggested Reply ─────────────────────┐
│ [draft text]                            │
│ Confidence: 94% | Source: [doc title]   │
│ [Use Reply] [Edit] [Regenerate] [Ignore]│
└─────────────────────────────────────────┘
```

### Events to track

- `suggestion.generated`, `suggestion.accepted`, `suggestion.edited`, `suggestion.rejected`
- Store in message metadata or analytics table

### Agent diagnostics (internal)

- Expandable panel: confidence breakdown, grounding, sources, decision, link to AI run trace
- Takeover / Return to AI controls in thread header

### Tasks

- [x] Wire `GET/PATCH /api/v1/ai/config` + channel overrides
- [x] Suggestion panel component + API for pending suggestions
- [x] AI run detail drawer (agent-only)
- [x] Hide all diagnostics from Web Chat customer view

---

## Phase 15 — Backend module structure (Day 4 target)

Align with spec layout under `backend/app/modules/ai/`:

```
ai/
├── domain/          models.py, schemas.py, interfaces.py
├── application/
│   ├── agent_service.py       (mode + pipeline orchestration)
│   ├── confidence_service.py  (explainable scoring)
│   ├── context_service.py     (ContextBuilder + memory)
│   ├── escalation_service.py  (handoff + tickets)
│   ├── evaluation_service.py  (suite runner)
│   ├── grounding_validator.py
│   └── prompt_service.py
├── infrastructure/
│   ├── langchain/   (if needed)
│   ├── langgraph/
│   ├── llm/
│   ├── retrieval/   (hybrid retriever, query preparer)
│   └── embeddings/
├── graphs/
│   └── support_agent.py
└── prompts/         (seed templates + render helpers)
```

Refactor incrementally; avoid big-bang moves that break Day 3 tests.

---

## Phase 16 — API summary (Day 4)

| Method | Path | Status |
|--------|------|--------|
| `GET` | `/api/v1/ai/config` | Extend (channel overrides, new flags) |
| `PATCH` | `/api/v1/ai/config` | Extend |
| `GET` | `/api/v1/ai/runs` | Extend (filters, trace summary) |
| `GET` | `/api/v1/ai/runs/{id}` | Extend (full trace + cost) |
| `POST` | `/api/v1/ai/test` | Existing |
| `GET` | `/api/v1/ai/evaluations` | **New** |
| `POST` | `/api/v1/ai/evaluations/run` | **New** |
| `POST` | `/api/v1/conversations/{id}/takeover` | **New** |
| `POST` | `/api/v1/conversations/{id}/return-to-ai` | **New** |
| `POST` | `/api/v1/conversations/{id}/ticket` | **New** |
| `GET` | `/api/v1/agents/availability` | **New** |
| `PATCH` | `/api/v1/agents/availability` | **New** |

RBAC: reuse `ai.read` / `ai.write` + agent permissions for takeover and availability.

---

## Day 4 acceptance tests

Manual or automated — all must pass before Done.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | **High-confidence Autopilot** — known FAQ | Correct article retrieved, grounded answer, confidence > threshold, AI replies |
| 2 | **Unknown question** | No relevant knowledge, no hallucination, ticket created with handoff summary |
| 3 | **Suggest Reply** | Suggestion shown to agent; AI does not send; agent accepts → agent message sent |
| 4 | **Agent takeover** | Autopilot active → takeover → `HUMAN_CONTROL`; AI cannot send customer messages |
| 5 | **Return to AI** | After return → next customer message processed by AI again |
| 6 | **Offline** | AI OFF + agents OFFLINE → customer message → timeout → ticket (`MISSED_CHAT`) |
| 7 | **Multilingual** | Spanish customer message → detected → grounded Spanish response |
| 8 | **Angry customer** | Negative/angry sentiment → HIGH priority + appropriate team routing |

### Suggested test files

- `backend/tests/test_day4_grounding.py`
- `backend/tests/test_day4_modes.py`
- `backend/tests/test_day4_takeover.py`
- `backend/tests/test_day4_missed_chat.py`
- `backend/tests/test_ai_evaluation.py` (full suite)

---

## Definition of Done

### AI runtime

- [x] Conversation context (customer, history, summary, ticket context, metadata)
- [x] Hybrid retrieval with reranking
- [x] Relevance threshold — can refuse weak knowledge
- [x] Grounding validation — blocks ungrounded Autopilot replies
- [x] Confidence engine with component scores
- [x] Explainable confidence (internal agents only)
- [x] Escalation logic with structured reasons
- [x] AI handoff package on every AI escalation

### Bot modes & control

- [x] Knowledge Base mode — deterministic
- [x] Suggest Reply mode — never auto-sends
- [x] Autopilot mode — confidence + grounding gated
- [x] Agent takeover (`HUMAN_CONTROL`)
- [x] Return to AI
- [x] AI kill switch — worker respects live config
- [x] Per-channel mode configuration

### Ticketing & routing

- [x] AI escalation tickets (`AI_ESCALATION`)
- [x] Missed chat tickets (`MISSED_CHAT`) with configurable timeout
- [x] Offline routing when AI + agents unavailable
- [x] Ticket source field on all auto-created tickets
- [x] Handoff summary visible on ticket

### AI operations

- [x] AI run step tracing (operational metadata)
- [x] Token usage per run
- [x] Estimated cost per run
- [x] Prompt versioning in DB; version recorded on each run
- [x] Evaluation framework with 20–30 seeded cases
- [x] Evaluation report API + baseline metrics

### Language & sentiment

- [x] Language detection on customer messages
- [x] Multilingual AI responses
- [x] Sentiment labels used for routing/priority

### Agent experience

- [x] AI suggestion panel (Use / Edit / Regenerate / Ignore)
- [x] Confidence + knowledge source display
- [x] Takeover and Return to AI controls
- [x] Suggestion lifecycle events tracked

### Boundary (explicitly out of scope)

- [x] No new channels (email, WhatsApp, etc.)
- [x] No tool calling / autonomous external actions
- [x] No Day 5 omnichannel architecture

---

## Success demo (end-to-end)

```
CUSTOMER → Web Chat → Conversation (Bot = AUTOPILOT)
  → LangGraph: Intent + Context + Hybrid Knowledge
  → Generation → Grounding → Confidence
  → if > 85%: AI Reply
  → if < 85%: Ticket + AI Handoff Summary
  → AIRun trace + token/cost logged
  → Agent opens inbox: sees confidence breakdown OR handoff on ticket
```

After Day 4 is stable, Day 5 adds email channel + unified omnichannel conversation architecture.

---

## Evaluation baseline (Echo LLM, offline)

First run via `POST /api/v1/ai/evaluations/run` or `pytest tests/test_day4_acceptance.py::test_evaluation_suite_runs_offline`:

| Metric | Typical offline baseline |
|--------|--------------------------|
| Cases | 25 |
| Intent accuracy | ~80–95% |
| Escalation accuracy | ~85–95% |
| Grounding rate | varies (no KB in offline eval) |
| Answer quality | ~70–90% |
