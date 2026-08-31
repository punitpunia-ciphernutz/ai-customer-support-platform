# Day 3 Implementation Plan — First Working AI Support Agent

**Goal:** Connect Support Core + Knowledge + LangGraph so a customer can ask a real support question in Web Chat and receive a grounded answer from the knowledge base—or get escalated to a human ticket when confidence is low.

**Rule:** WebSocket/HTTP must not wait for the LLM. AI runs asynchronously via Celery. One LangGraph Support Agent graph—no tool calling, no multi-agent.

**Depends on:** Day 1 (conversations, messages, tickets, Celery, Redis events, WebSocket) + Day 2 (knowledge retrieval, `AIService`, classification graph, `AIRun`).

**Key existing hooks (extend, don’t fork):**

| Area | Path |
|------|------|
| Message event | `ConversationService._publish_message` → `message.created` |
| AI boundary | `backend/app/modules/ai/application/ai_service.py` |
| Day 2 classify graph | `backend/app/modules/ai/graphs/classification.py` |
| Retriever | `backend/app/modules/knowledge/infrastructure/vectorstore/retriever.py` |
| Celery | `backend/app/workers/tasks.py` (add AI task beside `ingest_document`) |
| `SenderType.AI` | Already in schema — use for AI replies |
| Inbox / Web Chat UI | `frontend/src/features/inbox/InboxPage.tsx`, `WebChatPage.tsx` |

---

## Acceptance demo (must work end-to-end)

### Flow A — AI resolve

1. Admin adds **Password Reset Guide** (TEXT) → Celery ingests → `COMPLETED`
2. Customer opens Web Chat → asks *"How do I reset my password?"*
3. Message saved → `message.created` → Celery → LangGraph Support Agent
4. Intent `ACCOUNT_ACCESS` → retriever finds guide → grounded answer → confidence ≥ threshold
5. AI message saved (`sender_type=AI`) → WebSocket → customer sees answer
6. `AIRun` row stored with intent, retrieval count, confidence, latency, tokens

### Flow B — Escalation

1. Customer asks *"Can you change my billing plan?"* (no actionable knowledge)
2. Low confidence / no relevant docs → escalate
3. Ticket created, team assigned, internal AI note added (customer does **not** see reasoning)
4. No duplicate AI reply on Celery retry

---

## Recommended order (critical path)

```
1. Schemas + DB (AIResponse, SupportAgentState, extend AIRun, ai_configs)
2. ContextBuilder (conversation history + customer)
3. Prompts layer (generation + rerank prompts, versioned)
4. Reranker / relevance evaluator (top 10 → top 3–5)
5. Confidence engine + escalation policy (configurable thresholds)
6. LangGraph Support Agent graph (full node chain + decision)
7. AIService.process_customer_message() + idempotency
8. Celery AI task + message.created subscriber
9. AI reply path (save message + event) + escalation (ticket + note)
10. AI APIs (test, runs, config) + org AI toggle/mode
11. React UI (AI bubbles, agent diagnostics panel)
12. Tests + demo both flows
```

```mermaid
flowchart TD
  msg[Customer_message] --> save[Save_message]
  save --> evt[message.created]
  evt --> celery[Celery_process_ai_message]
  celery --> idem{Already_processed?}
  idem -->|yes| skip[Skip]
  idem -->|no| run[AIRun_PENDING]
  run --> graph[LangGraph_Support_Agent]
  graph --> ctx[ContextBuilder]
  graph --> intent[Classify_Intent]
  graph --> retr[Retrieve_+_Rerank]
  graph --> gen[Grounded_Generation]
  graph --> conf[Confidence_Engine]
  conf --> dec{Decision}
  dec -->|resolve| aiMsg[Save_AI_message]
  dec -->|escalate| ticket[Create_ticket_+_note]
  aiMsg --> ws[WebSocket]
  ticket --> ws
```

**Parallel after Phase 1:** Prompts + reranker can be built while graph skeleton is wired. UI can start once AI message shape is stable.

---

## Phase 1 — Domain models, schemas & migration

**Unlocks:** everything else

### Extend `AIRun` (`backend/app/modules/ai/domain/models.py`)

Add fields for agent analytics (nullable where needed for Day 2 classify runs):

| Field | Purpose |
|-------|---------|
| `graph_version` | e.g. `support-agent-v1` |
| `intent` | Final intent label |
| `retrieval_count` | Docs/chunks used |
| `confidence` | Final support confidence |
| `processing_key` | Idempotency: unique per `message_id` (or `conversation_id`+`message_id`) |

Extend `AIRunType`: add `AGENT` (or `SUPPORT_AGENT`).  
Align lifecycle with spec: `PENDING` → `RUNNING` → `COMPLETED` | `FAILED` (map existing `SUCCEEDED` → `COMPLETED` or add alias).

### New `AIConfig` (org-scoped)

Table `ai_configs` (one row per org):

| Field | Default (dev) |
|-------|----------------|
| `enabled` | `true` |
| `mode` | `DRAFT_ONLY` \| `SUGGEST` \| `AUTO_REPLY` — default **`DRAFT_ONLY`** or controlled `AUTO_REPLY` |
| `auto_reply_threshold` | `0.85` |
| `escalation_threshold` | `0.85` |
| `allowed_intents` | optional JSON list |
| `restricted_intents` | e.g. `["OTHER"]` |

Alembic: `0004_day3_ai_agent.py`.

### Pydantic schemas (`backend/app/modules/ai/domain/schemas.py`)

- **`SupportAgentState`** — typed graph state (Pydantic `BaseModel` or `TypedDict` + validators):
  - `conversation_id`, `message_id`, `organization_id`
  - `customer_context`, `conversation_history`, `user_message`
  - `intent`, `intent_confidence`
  - `retrieved_documents`, `retrieval_score`
  - `draft_response`, `support_confidence`, `sentiment`
  - `escalation_required`, `escalation_reason`, `final_response`
- **`AIResponse`** — structured output:
  - `answer`, `intent`, `confidence`, `grounded`, `escalation_required`, `escalation_reason`, `citations[]`
- **`Citation`**: `document_id`, `title` (chunk id optional in metadata)
- API DTOs: `AITestRequest`, `AITestResponse`, `AIConfigUpdate`, `AIRunSummary`

### Tasks

- [x] Migration + models
- [x] Seed default `AIConfig` for demo org (migration or startup hook)
- [x] Message metadata shape for AI replies: `{ "ai_run_id", "confidence", "intent", "grounded", "citations" }` (store in `messages.metadata_`)

---

## Phase 2 — Conversation & customer context

**Path:** `backend/app/modules/ai/application/context_builder.py` (new)

### ContextBuilder

```
Conversation + message_id
  → recent messages (last N, e.g. 10–20, token-budget cap)
  → customer record (name, email, company, metadata)
  → conversation metadata (channel, status)
  → payload for graph
```

- Load from `ConversationService` / message repo — **no** long-term memory
- Format history for prompts: labeled turns (`Customer:` / `Agent:` / `AI Support:`)
- Unit test: multi-turn login example from spec resolves with full context, not last message only

### Tasks

- [x] `ContextBuilder.build(conversation_id, message_id) -> CustomerContext + history`
- [x] Reuse in Support Agent graph **and** `POST /ai/test` (optional synthetic customer)

---

## Phase 3 — Intent detection (inside agent)

Reuse Day 2 classifier node/logic — move or wrap `classification.py` as `classify_intent` node.

- Input: `user_message` + light context
- Output: `{ intent, confidence }` → store on `SupportAgentState` and `AIRun`
- Intents: existing `IntentLabel` enum
- Policy hooks: `OTHER` → escalation candidate; explicit human request → `requires_human` / `escalation_required`

### Tasks

- [x] Graph node `classify_intent` calling `LLMProvider.structured_output` → `AIClassification`
- [x] Detect “speak to a human” via intent + keyword guard (billing escalation phrase list minimal)

---

## Phase 4 — Knowledge retrieval + relevance evaluation

**Retriever:** existing `PgVectorRetriever.search(organization_id=...)`.

### Flow

```
user_message (+ optional intent-enriched query)
  → vector search top_k=10
  → relevance evaluation / rerank
  → top 3–5 chunks → graph state
```

### Reranker (`backend/app/modules/ai/infrastructure/reranker.py`)

Keep simple for Day 3:

- **Option A (preferred):** LLM structured score per chunk (0–1) via small prompt in prompts layer
- **Option B:** weighted blend of vector score + keyword overlap

Do **not** dump 20 docs into the generation prompt.

### Tasks

- [x] `Reranker.rank(query, hits) -> list[RetrievalHit]` with `retrieval_score` aggregate
- [x] Graph nodes: `retrieve_knowledge`, `evaluate_retrieved_context`
- [x] Empty/low-score results → flag `escalation_required` early

---

## Phase 5 — Grounded response generation

**Path:** `backend/app/modules/ai/prompts/` (versioned templates, not inline strings)

### Generation prompt (conceptual sections)

1. System: support agent rules (no invention, no fake actions, concise, ask clarification)
2. `COMPANY KNOWLEDGE:` reranked chunks with titles
3. `CUSTOMER:` name, company
4. `CONVERSATION:` recent history
5. `CURRENT MESSAGE:`

### Tasks

- [x] `prompts/support_agent_v1.py` (or YAML) with `render_generate_prompt(state)`
- [x] Graph node `generate_answer` → `draft_response` + `grounded` flag + `citations`
- [x] If knowledge insufficient: answer admits gap (feeds confidence + escalation)

---

## Phase 6 — Confidence engine & escalation policy

**Path:** `backend/app/modules/ai/application/confidence.py`

### Deterministic scoring (no ML)

| Signal | Source |
|--------|--------|
| Intent confidence | classify node |
| Retrieval relevance | reranker avg / max |
| Grounding | citations present + LLM `grounded` flag |
| Context completeness | history length / required fields |
| Response validation | non-empty, no policy violations |

Example: weighted mean → `support_confidence` (document weights in settings or `AIConfig`).

### Escalation policy (`escalation.py`)

Configurable via `AIConfig`:

| Condition | Action |
|-----------|--------|
| `confidence < escalation_threshold` | Escalate |
| No relevant knowledge (score < min) | Escalate |
| Customer asks for human | Escalate |
| `intent == OTHER` | Escalate |
| `confidence >= auto_reply_threshold` | AI resolve (if mode allows) |

Graph node `calculate_confidence` → `decision` (`AI_RESOLVE` | `ESCALATE`).

### Tasks

- [x] Pure functions + unit tests with fixed inputs
- [x] `AIConfig` thresholds drive policy (no hard-coded 0.85 in graph)

---

## Phase 7 — LangGraph Support Agent graph

**Path:** `backend/app/modules/ai/graphs/support_agent.py`

### Node chain

```
START
  → load_conversation
  → load_customer
  → classify_intent
  → retrieve_knowledge
  → evaluate_retrieved_context
  → generate_answer
  → calculate_confidence
  → decision
      ├─ AI_RESOLVE → finalize_response → END
      └─ ESCALATE   → prepare_escalation_summary → END
```

- State: `SupportAgentState` (typed)
- No tool calling nodes
- `AIService.run_support_agent(conversation_id, message_id)` orchestrates DB session, creates/updates `AIRun`, returns `AIResponse`
- Reuse Day 2 `timed_*` pattern for latency measurement

### Tasks

- [x] Compile graph + fallback if LangGraph unavailable (dev echo)
- [x] `graph_version` constant on compile
- [x] Persist intent, retrieval_count, confidence, token_usage on `AIRun` completion

---

## Phase 8 — Idempotency & AI Run lifecycle

### Idempotency

Before processing `message_id`:

```
SELECT ai_runs WHERE message_id = ? AND type = AGENT
  → COMPLETED / SUCCEEDED / RUNNING / PENDING → skip (return existing)
  → FAILED → reuse same run (PENDING → RUNNING → retry)
  → none → insert PENDING with unique processing_key
```

On start: insert `AIRun` `PENDING` → `RUNNING` with unique `processing_key` (`f"{conversation_id}:{message_id}"`).

AI replies store `metadata.trigger_message_id`; `_save_ai_reply` skips if a reply already exists for that trigger.

Unique constraint on `processing_key` prevents duplicate run rows.

### Lifecycle

`PENDING` → `RUNNING` → `COMPLETED` | `FAILED` (store `error` on failure)

Implemented in `AIService._acquire_agent_run()` + `run_support_agent()`.

### Tasks

- [x] DB constraint / service-level guard
- [x] Celery `max_retries` safe with idempotency (retries reuse FAILED run, no duplicate AI messages)
- [x] Test: duplicate `message_id` skips second run
- [x] Test: FAILED run retry reuses same `AIRun` row
- [x] Test: lifecycle observes PENDING → RUNNING → COMPLETED

---

## Phase 9 — Celery async wiring (Conversation → AI)

**Path:** `backend/app/workers/tasks.py` + new subscriber

### Flow

```
FastAPI saves customer message
  → message.created (Redis)
  → subscriber enqueues Celery task (or task triggered from event handler)
  → process_ai_message(message_id)
  → AIService.run_support_agent(...)
```

### Subscriber options

- **A:** Redis subscriber in worker process listening to `message.created` (filter `sender_type=CUSTOMER`)
- **B:** Lightweight handler in API process that only `.delay()`’s Celery (still async for WS)

Check `AIConfig.enabled` and `mode` before processing.

| Mode | Behavior |
|------|----------|
| `DRAFT_ONLY` | Run agent, save run, optionally internal note/draft — **no** customer message |
| `SUGGEST` | Run agent, expose to agents (inbox metadata) — optional for Day 3 |
| `AUTO_REPLY` | Full resolve/escalate path |

### Tasks

- [x] `process_ai_message` Celery task (async SQLAlchemy session pattern like `ingest_document`)
- [x] Only trigger for `sender_type=CUSTOMER` + `AIConfig.enabled`
- [x] Do not block WebSocket or HTTP response

---

## Phase 10 — AI response + WebSocket

### On AI resolve (`AUTO_REPLY`)

1. `ConversationService` (or dedicated `AIMessageService`) saves `Message`:
   - `sender_type=AI`, `sender_id=null` or system id
   - `content=answer`
   - `metadata_` = intent, confidence, citations, `ai_run_id`
2. `_publish_message` → existing WebSocket path (`inbox/ws.py` fan-out)
3. Mark `AIRun` `COMPLETED`

### Customer vs agent visibility

| Audience | Sees |
|----------|------|
| Web Chat | Answer text only (friendly “AI Support” label) |
| Agent Inbox | Intent, confidence, knowledge titles, status badge |

### Tasks

- [x] Ensure public WS receives AI messages for conversation
- [x] No internal escalation reasoning in customer-visible content

---

## Phase 11 — Human ticket escalation

**On escalate:** use existing tickets module (`backend/app/modules/tickets/router.py`).

### Flow

1. Generate escalation summary (LLM `summarize` or template from state)
2. `POST` ticket via service:
   - Title from intent + snippet
   - `assigned_team_id` from intent→team map (config table or simple dict: `BILLING` → billing team)
   - Link `conversation_id` / `customer_id`
3. Add **internal note** message (`sender_type=SYSTEM` or agent-only metadata) with:
   - Reason, intent, confidence, knowledge searched, attempted response, recommendation

### Tasks

- [x] `EscalationService.create_from_ai_run(state, ai_run_id)`
- [x] Intent → team routing (minimal config in `AIConfig` or settings)
- [x] Customer sees short handoff message optional: *"Connecting you with our team."* (only if spec/demo requires)

---

## Phase 12 — AI APIs

**Router:** extend `backend/app/modules/ai/api/routes.py`

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/ai/test` | Run agent pipeline without saving customer message (dev speed) |
| `GET` | `/api/v1/ai/runs` | List runs (org-scoped, paginated) |
| `GET` | `/api/v1/ai/runs/{id}` | Run detail + output |
| `GET` | `/api/v1/ai/config` | Org AI settings |
| `PATCH` | `/api/v1/ai/config` | Toggle enabled, mode, thresholds |

Permissions: `ai.read` / `ai.write` (or reuse admin permissions).

### `POST /ai/test` body/response

```json
// Request
{ "message": "How do I reset my password?", "conversation_id": null }

// Response
{
  "intent": "ACCOUNT_ACCESS",
  "confidence": 0.94,
  "grounded": true,
  "answer": "...",
  "sources": [{ "document_id": "...", "title": "Password Reset Guide" }],
  "escalation_required": false
}
```

Keep `POST /ai/classify` for backward compatibility.

### Tasks

- [x] Wire routes in `api/router.py`
- [x] RBAC + org scoping on runs/config

---

## Phase 13 — React AI conversation UI

### Web Chat (`WebChatPage.tsx`)

- Distinct bubble style for `sender_type === "AI"` (label: **AI Support**)
- Hide confidence/citations from customer

### Agent Inbox (`InboxPage.tsx`)

- AI bubble styling (`.bubble.ai`)
- Expandable **AI Information** panel when metadata present:
  - Intent, confidence %, knowledge titles, status (e.g. AI Resolved / Escalated)
- Optional: settings page or modal for **AI Support ON/OFF** + mode radio (`DRAFT_ONLY` / `SUGGEST` / `AUTO_REPLY`)

### Tasks

- [x] Update `Message` type for AI metadata
- [x] CSS consistent with Day 1 patterns
- [x] WS invalidation already handles `message.created` — verify AI messages refresh thread

---

## Phase 14 — Tests

**Path:** `backend/tests/test_day3_*.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Known question: *"How do I reset my password?"* | AI answer, high confidence, citation |
| 2 | Unknown: *"Can you change my company's billing plan?"* | Escalation, ticket, no false action |
| 3 | Ambiguous: *"It isn't working."* | Clarification question or escalation |
| 4 | Human request: *"I want to speak to a human."* | Immediate escalation |
| 5 | Unsupported: *"Does your product integrate with XYZ?"* | No hallucination; escalate/clarify |
| 6 | Multilingual: *"¿Cómo restablezco mi contraseña?"* | Spanish response, correct intent |

### Backend tests

- [x] Unit: `ContextBuilder`, confidence engine, escalation policy
- [x] Unit: reranker with mocked hits
- [x] Unit: idempotency — duplicate `message_id` skips second run
- [x] Unit: FAILED run retry reuses same `AIRun` without duplicate rows
- [x] Unit: lifecycle PENDING → RUNNING → COMPLETED
- [x] Integration: seeded FAQ → `POST /ai/test` → grounded + citation
- [x] Integration: Celery task path → AI message + `AIRun COMPLETED` + `message.created` event
- [x] Integration: low-confidence path → ticket + internal note, no AI customer message
- [x] Integration: ambiguous question (*"It isn't working."*) → clarification or escalation
- [x] Integration: unsupported integration (*"Does your product integrate with XYZ?"*) → no hallucination, escalation
- [x] Regression: classify endpoint still works; no auto-reply when `AIConfig.enabled=false`

**Test file:** `backend/tests/test_day3_agent.py` — **17 tests**

### Frontend

- [x] Smoke: AI bubble renders in inbox and web chat with seeded conversation

---

## Database & API summary

### New / changed tables

| Table | Purpose |
|-------|---------|
| `ai_runs` | Extended columns + `AGENT` type + idempotency key |
| `ai_configs` | Org AI toggle, mode, thresholds |
| `messages.metadata_` | AI reply diagnostics (JSONB, no migration if already JSONB) |

### Out of scope (Day 3)

Stripe/CRM/Jira actions, tool calling, MCP, playbooks, voice/WhatsApp/Slack, advanced analytics, multi-agent.

---

## Definition of Done checklist

### Core pipeline

- [x] Customer message triggers async AI via Celery (not blocking WS)
- [x] LangGraph Support Agent with full node chain
- [x] Typed `SupportAgentState`
- [x] `ContextBuilder` (history + customer)
- [x] Intent detection inside agent (Day 2 classifier reused)
- [x] LangChain/pgvector retrieval + rerank to top 3–5
- [x] Versioned grounded generation prompt
- [x] Structured `AIResponse` with citations
- [x] Deterministic confidence engine
- [x] Configurable escalation policy
- [x] Human escalation → ticket + internal AI note
- [x] AI reply saved + delivered via WebSocket
- [x] Idempotency prevents duplicate AI responses (including FAILED-run Celery retries)
- [x] `AIRun` lifecycle `PENDING` → `RUNNING` → `COMPLETED`/`FAILED` + analytics fields persisted

### APIs & config

- [x] `POST /api/v1/ai/test`
- [x] `GET /api/v1/ai/runs`, `GET /api/v1/ai/runs/{id}`
- [x] `GET/PATCH /api/v1/ai/config`
- [x] Org AI toggle + mode (`DRAFT_ONLY` default for safe dev)

### UI

- [x] Web Chat: customer sees AI Support replies
- [x] Inbox: agents see AI diagnostics (not exposed to customer)

### Demos & tests

- [x] Flow A (password reset) demo passes
- [x] Flow B (billing escalation) demo passes
- [x] All 6 spec test scenarios covered
- [x] Celery → AI → WebSocket event path covered in tests
- [x] `docs/day3-audit.md` — final audit (all requirements complete)

---

## Target architecture (end of Day 3)

```
CUSTOMER → Web Chat → FastAPI → ConversationService → message.created
                              ↓
                           Celery → AIService → LangGraph Support Agent
                              ├── ContextBuilder (customer + history)
                              ├── Intent (Day 2 classifier)
                              ├── Retriever + Reranker (pgvector)
                              ├── Grounded generation (prompts/)
                              ├── Confidence engine
                              └── Decision
                                    ├─ AI Message → WebSocket
                                    └─ Ticket + internal note → WebSocket
```

**Next (Day 4 preview):** Better retrieval, citation quality, confidence calibration, prompt versioning, evaluation suite—before actions and integrations.
