# Day 6 Implementation Plan — Automation & Routing

**Goal:** Build a reusable, deterministic automation engine that reacts to support events and executes actions across conversations, tickets, customers, teams, and notifications — without hardcoded business rules.

**Principle:** Execution engine first. No visual workflow builder. AI provides structured signals; automation applies deterministic business logic.

**Rule:** Everything enters through the existing event system. The automation engine orchestrates separate services (assignment, business hours, SLA, notifications) — it does not own their logic.

**Depends on:** Day 5 complete (omnichannel, unified inbox, event bus, Celery, AI intent/sentiment on `AIRun`, manual assignment fields on `Conversation`/`Ticket`).

**Status:** **COMPLETE** (2026-09-02) — migration `0008_day6_automation`, **25/25** Day 6 tests, audit fix pass, re-audit **COMPLETE**

## Target architecture

```
SUPPORT EVENT (message.received, ticket.created, AI_ESCALATED, …)
        │
        ▼
Automation Trigger Matcher  ←── event bus subscriber (in-process)
        │
        ▼
Build AutomationContext (from domain objects + AI signals)
        │
        ▼
Evaluate condition tree (AND/OR)
        │
   FALSE ──► STOP
   TRUE  ──► Action registry → Assignment / Tags / Priority / Notify / …
        │
        ▼
AutomationExecution + Steps (observability)
        │
        ▼
Audit / downstream events (loop-safe, idempotent)
```

**Domain separation (keep distinct):**

| Service | Owns |
|---------|------|
| Automation engine | Trigger match, condition eval, action dispatch |
| AssignmentService | Who gets the work (team/user/round-robin) |
| BusinessHoursService | Is support operating? |
| SLAService | When is work due? |
| NotificationService | Who needs to know? |

---

## Existing hooks (extend, don't fork)

| Area | Path | Day 6 note |
|------|------|------------|
| Event bus (Redis pub/sub) | `backend/app/infrastructure/events/bus.py` | Add in-process subscriber; do not call automation from every service directly |
| Published events | `conversations/service.py`, `tickets/`, `escalation_service.py` | Extend/normalize names to match trigger enum; emit AI signals |
| Teams + assignment fields | `models.py` — `Team`, `assigned_*` on `Conversation`/`Ticket` | Wire via `AssignmentService`, not inline in engine |
| Agent availability (basic) | `modules/ai/domain/models.py` — `AgentAvailability.is_online` | Expand to `ONLINE` / `AWAY` / `OFFLINE` + active count |
| Business hours (AIConfig JSONB) | `AIConfig.business_hours`, `availability_service.py` | Migrate to dedicated `BusinessHours` entity; keep AIConfig fallback during transition |
| Missed chat (polling) | `missed_chat_service.py`, beat `process_missed_chats` | Refactor to per-conversation Celery delayed task + state re-check |
| Hardcoded intent routing | `escalation_service.py` — `intent_team_map` | Replace with default automations; deprecate map for routing |
| Celery pattern | `workers/tasks.py`, `tasks_bridge.py` | Add automation execution + missed-chat delay tasks |
| Audit | `infrastructure/audit.py` | Log automation executions alongside domain audit |
| Frontend shell | `AppShell.tsx`, `router.tsx` | Add `/automations`, `/settings/business-hours`; availability in inbox header |
| Latest migration | `0007_day5_omnichannel` | Next: `0008_day6_automation` |

**Gaps to build:** `modules/automation/`, tags, notifications, SLA, action registry, execution logs, loop protection.

**Module layout** (follow existing `modules/` convention):

```
backend/app/modules/automation/
├── domain/          models.py, enums.py, schemas.py
├── application/     automation_service, trigger/condition/action/execution services
├── infrastructure/  repositories.py, scheduler.py (Celery enqueue)
└── api/             routes.py, schemas.py
```

Plus standalone services: `modules/assignment/`, `modules/notifications/`, `modules/sla/`, `modules/business_hours/` (or colocate under automation if small).

---

## Recommended implementation order (critical path)

```
 1.  DB migration — automation, execution logs, tags, business hours, SLA, notifications
 2.  BusinessHoursService + holidays (timezone-aware open/closed)
 3.  Agent availability expansion (ONLINE/AWAY/OFFLINE, active count)
 4.  AssignmentService (team, user, round-robin, find_available_agent)
 5.  NotificationService + preferences (in-app + email foundation)
 6.  Tag model + add/remove tag actions
 7.  Automation domain models + CRUD repositories
 8.  AutomationContext builder (conversation, ticket, message, AI signals)
 9.  Condition evaluator (operators + AND/OR JSON tree)
10.  Action registry + idempotent handlers
11.  ExecutionService (logs, steps, errors, loop protection)
12.  Event bus subscriber → trigger matcher → queue/sync execute
13.  Celery task for heavy/multi-write action chains
14.  SLA foundation (policy + timer create/pause/breach)
15.  Missed chat — delayed Celery task per conversation (replace polling-only path)
16.  AI signal events (AI_ESCALATED, AI_LOW_CONFIDENCE) + migrate intent_team_map
17.  Default automation seeds (billing, angry, escalation, reopen, missed chat)
18.  REST APIs (automations, business-hours, availability, notifications)
19.  Frontend — automation list/form/detail, business hours, inbox availability
20.  Day 6 test suite + acceptance scenario
```

---

## Phase 1 — Database & domain models

**Unlocks:** persistence for rules, logs, routing, SLA, notifications

### New entities

| Entity | Key fields |
|--------|------------|
| `Automation` | `organization_id`, `name`, `description`, `enabled`, `trigger` (JSONB), `conditions` (JSONB tree), `actions` (JSONB array), `priority`, `created_by` |
| `AutomationExecution` | `automation_id`, `organization_id`, `trigger_event`, `entity_type`, `entity_id`, `status`, `started_at`, `completed_at`, `error`, `metadata` |
| `AutomationExecutionStep` | `execution_id`, `step_type`, `configuration`, `status`, `result`, `error`, `duration_ms` |
| `BusinessHours` | `organization_id`, `name`, `timezone`, `is_default` |
| `BusinessHoursSchedule` | `business_hours_id`, `day_of_week`, `open_time`, `close_time`, `closed` |
| `BusinessHoliday` | `business_hours_id`, `date`, `name` |
| `AgentAvailability` (extend) | Add `status` enum, `last_seen_at`, `active_conversation_count`; migrate `is_online` → status |
| `SLAPolicy` | `name`, `first_response_minutes`, `resolution_minutes`, `business_hours_id`, `applies_to` (JSONB), `enabled` |
| `SLATimer` | `conversation_id`, `ticket_id`, `type`, `started_at`, `due_at`, `paused_at`, `completed_at`, `breached_at`, `status` |
| `Notification` | `user_id`, `event_type`, `title`, `body`, `read_at`, `metadata` |
| `NotificationPreference` | `user_id`, `event_type`, `in_app`, `email`, `enabled` |
| `Tag` | `organization_id`, `name`, `color` (optional) |
| `ConversationTag` | `conversation_id`, `tag_id` |
| `TicketTag` | `ticket_id`, `tag_id` |

### Enums (store in domain)

- **Triggers:** conversation (created/updated/assigned/reopened/closed), message (received/sent), ticket (created/updated/assigned/resolved/reopened), AI (escalated/resolved/low_confidence), customer (created/updated), `MISSED_CHAT`
- **Condition operators:** EQUALS, NOT_EQUALS, CONTAINS, NOT_CONTAINS, STARTS_WITH, ENDS_WITH, IN, NOT_IN, GREATER_THAN, LESS_THAN, GREATER_OR_EQUAL, LESS_OR_EQUAL, IS_EMPTY, IS_NOT_EMPTY
- **Actions:** ASSIGN_TEAM, ASSIGN_USER, ASSIGN_ROUND_ROBIN, SET_PRIORITY, SET_STATUS, ADD_TAG, REMOVE_TAG, CREATE_TICKET, ASSIGN_TICKET, SET_TICKET_PRIORITY, ENABLE_AI, DISABLE_AI, ESCALATE_TO_HUMAN, NOTIFY_AGENT, NOTIFY_TEAM, NOTIFY_MANAGER
- **SLA timer types:** FIRST_RESPONSE, RESOLUTION — statuses: RUNNING, PAUSED, COMPLETED, BREACHED
- **Agent status:** ONLINE, AWAY, OFFLINE

### Alembic

- Migration: `0008_day6_automation.py`
- Document in `docs/database/day6-schema.md`
- Index: `(organization_id, enabled, priority)` on automations; `(entity_type, entity_id)` on executions

### Tasks

- [x] SQLAlchemy models + Pydantic request/response schemas
- [x] Unique constraint on `(organization_id, tag.name)`
- [x] Seed: default business hours (Mon–Fri 09:00–18:00, org timezone)
- [x] Seed: default SLA policies (optional, disabled by default)

---

## Phase 2 — Business hours + holidays

**Unlocks:** SLA due-date math, missed-chat context, future AI off-hours behavior

### BusinessHoursService

Methods: `is_open(org_id, dt)`, `next_open_time(...)`, `next_close_time(...)`

- Use explicit IANA timezone on `BusinessHours` (e.g. `Asia/Kolkata`) — never server TZ
- Holidays override weekly schedule (closed all day)
- Wire org default hours; link `SLAPolicy.business_hours_id`

### Tasks

- [x] CRUD repository + service
- [x] Unit tests: inside hours, outside hours, holiday, timezone edge (UTC vs local midnight)
- [x] Deprecate direct reads of `AIConfig.business_hours` in new code paths (keep fallback for Day 4 AI availability check until migrated)

---

## Phase 3 — Agent availability + assignment

**Unlocks:** round-robin, auto-assignment actions, missed-chat gate

### Agent availability

Extend `AgentAvailability`:

```
user_id, status (ONLINE|AWAY|OFFLINE), last_seen_at,
active_conversation_count, updated_at
```

- PATCH `/agents/me/availability` — inbox header dropdown (Online / Away / Offline)
- Assignment prefers ONLINE; optional org setting to allow AWAY fallback; never auto-assign OFFLINE unless action explicitly sets `allow_offline: true`
- Increment/decrement `active_conversation_count` on assign/unassign/close

### AssignmentService (separate from automation engine)

Methods: `assign_team()`, `assign_user()`, `assign_round_robin(team_id)`, `find_available_agent(team_id)`

- Round-robin: deterministic cursor per team (store `last_assigned_user_id` on team or separate cursor table); pick lowest `active_conversation_count` among eligible ONLINE agents as tie-breaker
- Skip no-op assigns (already assigned to same team/user)
- Emit `conversation.assigned` / `ticket.assigned` events (automation subscribes — loop protection required)

### Tasks

- [x] AssignmentService with round-robin cursor
- [x] Availability API updates (extend existing `agents/router.py`)
- [x] Tests: online assigned, offline skipped, round-robin order

---

## Phase 4 — Notification service + preferences

**Unlocks:** NOTIFY_* actions, agent awareness

### NotificationService

```python
notification_service.notify(recipient, event="TICKET_ASSIGNED", context={...})
```

- Channels: **IN_APP** (persist `Notification` row + WS event `notification.created`), **EMAIL** (foundation — queue or sync send via existing email infra; full templates later)
- Respect `NotificationPreference` per user/event_type
- Default preferences seeded for common events

### Tasks

- [x] Notification + preference models and APIs
- [x] In-app notification list + mark read
- [x] Preference PATCH API
- [x] Action handlers: NOTIFY_AGENT, NOTIFY_TEAM, NOTIFY_MANAGER

---

## Phase 5 — Automation engine core

**Unlocks:** the execution engine itself

### AutomationContext

Built from domain objects at execution time:

```
organization_id, conversation_id, customer_id, ticket_id, message_id,
channel, status, priority, intent, sentiment, ai_confidence,
assigned_team_id, assigned_user_id, tags[], custom metadata
```

- Populate from `Conversation`, `Message`, latest `AIRun`, `Customer`
- Read-only snapshot for one execution; no LLM calls inside engine

### Trigger matcher

Map `DomainEvent.name` → trigger enum (e.g. `message.received` → `MESSAGE_RECEIVED`)

- Load active automations for org where `trigger.type` matches, ordered by `priority DESC`, then `created_at`
- Controlled trigger set only (spec §5) — no trigger sprawl

### Condition evaluator

- JSON tree: `{ "logic": "AND"|"OR", "conditions": [...] }` — leaves are `{ field, operator, value }`
- Field resolver reads from `AutomationContext` (dot paths: `intent`, `conversation.status`, `channel`)
- Support nested AND/OR groups; no custom expression language

### Action registry

Pluggable handlers keyed by action type; each receives `(context, config, execution_step)`

- Assignment actions → `AssignmentService`
- Tag actions → tag service (idempotent add/remove)
- Priority/status → conversation/ticket service with no-op skip if unchanged
- Ticket create → existing ticket service
- AI actions → existing AI config / escalation hooks
- Notify actions → `NotificationService`

### Execution model

```
Event → match automations → (Celery if heavy) → build context
     → evaluate conditions → execute actions sequentially → record steps
```

- `ExecutionService` creates `AutomationExecution` + `AutomationExecutionStep` per condition/action
- Status: RUNNING → COMPLETED | FAILED | SKIPPED
- Record `duration_ms`, `error`, `result` JSON on each step

### Loop protection + idempotency

- Propagate `automation_execution_id` + `execution_depth` in event metadata
- `max_execution_depth` (default 3) — stop and log when exceeded
- Skip actions that would not change state (priority already HIGH, tag already present)
- Idempotent: duplicate ADD_TAG, safe retry of ASSIGN_TEAM
- Destructive actions (CREATE_TICKET): idempotency key = `(automation_id, entity_id, trigger_event_id)`

### Tasks

- [x] AutomationContext builder
- [x] Condition evaluator with all operators
- [x] Action registry with initial action set
- [x] ExecutionService + repositories
- [x] Enable/disable automation (no delete required for acceptance)
- [x] Synchronous path for simple actions; Celery for notify + ticket create chains

---

## Phase 6 — Event bus → automation integration

**Unlocks:** decoupled entry point (spec §26)

### In-process subscriber

- On app startup: subscribe to Redis channel **or** add synchronous hook in `event_bus.publish()` for local handlers (prefer lightweight in-process registry called after publish)
- Flow: `MessageCreated` → bus → `AutomationTriggerHandler` → enqueue execution
- **Do not** call automation from `message_service.create()` directly — only emit events

### Events to add/normalize

| Emit from | Event | Trigger |
|-----------|-------|---------|
| ConversationService | `conversation.created` | CONVERSATION_CREATED |
| ConversationService | `conversation.updated` | CONVERSATION_UPDATED |
| AssignmentService | `conversation.assigned` | CONVERSATION_ASSIGNED |
| ConversationService | `conversation.closed` / reopen | CONVERSATION_CLOSED / REOPENED |
| Message path | `message.received`, `message.sent` | MESSAGE_RECEIVED / SENT |
| TicketService | `ticket.*` | TICKET_* |
| AI pipeline | `ai.escalated`, `ai.low_confidence` | AI_ESCALATED / AI_LOW_CONFIDENCE |
| Missed chat task | `missed_chat` | MISSED_CHAT |

### Tasks

- [x] Automation event handler registered at startup
- [x] AI events emitted after classification/escalation (intent, sentiment, confidence in payload)
- [x] Integration test: message.received → automation executes → assignment logged

---

## Phase 7 — SLA foundation + timers

**Unlocks:** due dates for first response and resolution (dashboard later)

### SLAService (foundation only)

- On conversation/ticket create (or priority change): start timers per matching `SLAPolicy.applies_to` (e.g. priority=HIGH)
- `due_at` calculated using `BusinessHoursService` (business-minutes, not wall-clock only)
- Pause on `WAITING_FOR_CUSTOMER`; resume on customer reply — persist `paused_at` / status
- On first agent reply: complete FIRST_RESPONSE timer; on resolve: complete RESOLUTION
- Breach: set `breached_at`, status BREACHED — hook for future alerts (Day 6: persist only)

### Tasks

- [x] SLAPolicy CRUD (API minimal or seed-only for Day 6)
- [x] Timer lifecycle wired to conversation/message/ticket events
- [x] Tests: business-hours-aware due_at, pause/resume, breach flag

---

## Phase 8 — Missed chat (Celery delayed jobs)

**Unlocks:** acceptance scenario — no agent → wait → ticket

### Refactor from polling-only

Current: beat job `process_missed_chats` scans `WAITING_FOR_AGENT` — **keep as safety net**, add primary path:

```
Conversation created (no agent available)
  → schedule Celery task ETA = now + missed_chat_timeout
  → task runs: re-check status + availability
  → if still unassigned and waiting → emit MISSED_CHAT → automation creates ticket
```

- Config: `missed_chat_timeout_minutes` (existing on `AIConfig` or org settings)
- State re-check is mandatory — if agent assigned before ETA, task no-ops
- Default automation: `WHEN MISSED_CHAT → CREATE_TICKET + ASSIGN_TEAM support`

### Tasks

- [x] `schedule_missed_chat_check(conversation_id, eta)` in scheduler
- [x] Celery task with idempotency key per conversation
- [x] Wire on conversation create when `!is_agent_available()`
- [x] Tests: timeout creates ticket; agent before timeout → no ticket

---

## Phase 9 — AI signal integration

**Unlocks:** billing routing, angry customer, escalation without hardcoded maps

### Separation of concerns

```
Customer message → AI classifies → structured signal on event payload
  → automation conditions (deterministic) → actions
```

- **Do not** put LLM reasoning inside automation
- Migrate `intent_team_map` routing in `escalation_service.py` to default "Route Billing" automation (keep map as fallback behind feature flag until seeds verified)
- Emit `AI_ESCALATED` when escalation triggers; include intent, sentiment, confidence in payload

### Default automations (seed)

| Name | Trigger | Conditions | Actions |
|------|---------|------------|---------|
| Route Billing | MESSAGE_RECEIVED | intent = BILLING | Assign Billing, HIGH, tag billing |
| Angry Customers | MESSAGE_RECEIVED | sentiment = ANGRY | URGENT, NOTIFY_MANAGER |
| AI Escalation | AI_ESCALATED | — | CREATE_TICKET, NOTIFY_TEAM |
| Reopen on reply | MESSAGE_RECEIVED | status = CLOSED | SET_STATUS OPEN |
| Missed Chat | MISSED_CHAT | — | CREATE_TICKET, ASSIGN_TEAM support |

### Tasks

- [x] AI event emission after `AIRun` persistence
- [x] Seed script inserts default automations (enabled for dev org)
- [x] Remove/disable hardcoded `if intent == billing` paths

---

## Phase 10 — Automation APIs

Base path: `/api/v1`

### Automations

```
GET    /automations
POST   /automations
GET    /automations/{id}
PATCH  /automations/{id}
DELETE /automations/{id}
POST   /automations/{id}/enable
POST   /automations/{id}/disable
GET    /automations/{id}/executions
GET    /automation-executions/{id}      # includes steps
```

### Business hours

```
GET    /business-hours
POST   /business-hours
PATCH  /business-hours/{id}
GET    /business-hours/{id}/holidays
POST   /business-hours/{id}/holidays
DELETE /business-hours/{id}/holidays/{holiday_id}
```

### Availability

```
GET    /agents/availability
PATCH  /agents/me/availability
```

### Notifications

```
GET    /notifications
PATCH  /notifications/{id}/read
GET    /notification-preferences
PATCH  /notification-preferences
```

### Tasks

- [x] RBAC: org-scoped; agents read own notifications/preferences
- [x] Validation: trigger/condition/action JSON schemas on create/update
- [x] OpenAPI tags: Automations, Business Hours, Notifications

---

## Phase 11 — Frontend (no visual builder)

**Unlocks:** manage rules, hours, availability without JSON editing

### Routes

| Route | Purpose |
|-------|---------|
| `/automations` | List automations (name, enabled, execution count, priority) |
| `/automations/new` | Create form: name, trigger, conditions, actions, priority, enabled |
| `/automations/:id` | Detail + execution history |
| `/settings/business-hours` | Weekly schedule + timezone + holidays |

### Automation list UI

```
Automations                                    [+ New]
Route Billing       ON    12 executions
Angry Customers     ON     8 executions
VIP Routing         OFF    0 executions
```

### Automation detail

- Read-only summary: WHEN / IF / THEN
- Execution history table: id, status, timestamp; drill-down to steps
- Enable/disable toggle

### Create/edit form

Structured fields (dropdowns for trigger, field, operator, action type) — JSON stored behind the API, not raw editor required for MVP

### Business hours UI

- Timezone selector
- Mon–Sun rows: open/close or Closed
- Holiday list add/remove

### Agent availability UI

- Inbox header: agent name + status indicator (● Online)
- Dropdown: Online / Away / Offline
- Calls `PATCH /agents/me/availability`

### Tasks

- [x] Nav link in `AppShell` → Automations
- [x] Settings sub-nav → Business Hours
- [x] Types in `frontend/src/types/index.ts` for Automation, Execution, BusinessHours
- [x] Reuse existing form/table patterns from Channels/Settings pages

---

## Phase 12 — Tests + Day 6 acceptance scenario

### Suggested test files

```
backend/tests/test_day6_phase1_models.py
backend/tests/test_day6_conditions.py
backend/tests/test_day6_actions.py
backend/tests/test_day6_execution_logs.py
backend/tests/test_day6_loop_protection.py
backend/tests/test_day6_idempotency.py
backend/tests/test_day6_assignment_round_robin.py
backend/tests/test_day6_availability.py
backend/tests/test_day6_business_hours.py
backend/tests/test_day6_missed_chat_delayed.py
backend/tests/test_day6_sla_timers.py
backend/tests/test_day6_notifications.py
backend/tests/test_day6_event_integration.py
backend/tests/test_day6_automation_api.py
backend/tests/test_day6_acceptance.py
```

### Test coverage matrix

| Area | Cases |
|------|-------|
| Triggers | conversation.created, ticket.created, message.received fire matching automations |
| Conditions | equals, contains, in, AND, OR, nested tree |
| Actions | assign team/user, set priority/status, add tag, create ticket, notify |
| Routing | online → assigned; offline → skipped; round-robin → correct agent |
| Business hours | inside, outside, holiday, timezone |
| Missed chat | unavailable → delay → ticket; agent arrives first → no ticket |
| Idempotency | same event twice → one effective state change |
| Loop protection | A updates → B updates → depth limit stops safely |
| SLA | timer created, business-hours due_at, breach on overdue |

### Day 6 acceptance scenario (single integration test)

```
1. Customer: "I was charged twice."
   → conversation created → AI: BILLING, confidence 0.96
   → automation: assign Billing, HIGH, tag billing, notify team
   → execution log COMPLETED with steps

2. Customer: "I'm extremely angry. Nobody is helping."
   → AI: ANGRY → automation: URGENT + notify manager

3. No agents online → customer starts chat
   → wait timeout (mock Celery ETA) → still no agent
   → MISSED_CHAT ticket created + assigned to support team
```

Run:

```bash
docker compose exec backend pytest -q tests/test_day6_*.py
```

Regression: Day 5 suite (23 tests) + Day 4 suite (26 tests) must stay green.

---

## Definition of Done

### Automation

- [x] Automation model + CRUD API
- [x] Enable / disable
- [x] Trigger system (controlled set)
- [x] Condition engine (all operators)
- [x] AND / OR condition groups (JSON tree)
- [x] Action registry + execution
- [x] Execution history (execution + steps)
- [x] Error handling (FAILED status, step errors)
- [x] Idempotency on actions
- [x] Loop protection (depth limit, no-op skip)

### Routing

- [x] Team assignment via AssignmentService
- [x] User assignment
- [x] Round robin (deterministic)
- [x] Agent availability ONLINE / AWAY / OFFLINE
- [x] Priority routing via automation
- [x] AI intent routing via automation (not hardcoded map)

### Business hours

- [x] Timezone on BusinessHours
- [x] Weekly schedule
- [x] Holidays
- [x] is_open / next_open / next_close

### Missed chat

- [x] Availability check on conversation create
- [x] Configurable timeout
- [x] Celery delayed job (primary) + state re-check
- [x] Automatic ticket via MISSED_CHAT automation

### Notifications

- [x] NotificationService abstraction
- [x] In-app notifications
- [x] Email notification foundation
- [x] Notification preferences

### SLA

- [x] SLA policy model
- [x] First-response timer
- [x] Resolution timer
- [x] Business-hours-aware due_at
- [x] Pause/resume foundation
- [x] Breach foundation (persist, no dashboard)

### Observability

- [x] AutomationExecution records
- [x] AutomationExecutionStep records
- [x] Action results + errors
- [x] Duration per step
- [x] Audit trail linkage

### Frontend

- [x] Automation list
- [x] Automation create/edit (structured form)
- [x] Enable/disable + detail view
- [x] Execution history UI
- [x] Business-hours settings
- [x] Agent availability in inbox

### Infrastructure

- [x] Migration `0008_day6_automation`
- [x] Schema doc `docs/database/day6-schema.md`
- [x] Default automations seeded
- [x] Day 6 test suite green
- [x] Day 5 + Day 4 regression green

### Boundary (explicitly out of scope)

- [ ] Visual drag-and-drop workflow builder
- [ ] LLM reasoning inside automation actions
- [ ] Full SLA dashboard / breach alerts UI
- [ ] Browser push notifications
- [ ] Skill-based / least-loaded routing (beyond basic round-robin)
- [ ] WhatsApp / new channels
- [ ] Help Center / chat widget (was incorrectly labeled Day 6 in Day 5 plan — deferred)

---

## Success demo (end-to-end)

```
CUSTOMER MESSAGE ("I was charged twice.")
  → Conversation core + AI (BILLING, 0.96)
  → Event bus: message.received
  → Automation: Route Billing
      ✓ condition intent=BILLING
      ✓ assign Billing team (round-robin to online agent)
      ✓ priority HIGH, tag billing
      ✓ notify Billing team
  → SLA first-response timer started (business-hours aware)
  → Agent sees conversation in inbox (Online status in header)

ANGRY follow-up → URGENT + manager notification

NO AGENTS ONLINE → chat started → Celery ETA 10m → re-check
  → MISSED_CHAT event → ticket created → support team assigned
  → execution log answers "why was this assigned?"
```

After Day 6, Day 7 adds **Agent Copilot** — AI inside the agent workflow on top of this routing foundation.

---

## Post-audit fix pass (2026-09-02)

Applied all items from [`docs/day6-audit.md`](day6-audit.md) initial audit:

1. **P1** — NOTIFY_TEAM team-name resolution; SLA lifecycle wiring; automation create/edit UI; clear `intent_team_map`
2. **P2** — All 16 action handlers; email stub; missed-chat schedule on create; loop depth; 10 new test files; manager + Billing member seed
3. **P3** — Editable business hours + holidays UI; execution step viewer; active count decrement; audit linkage; `conversation.reopened`; Celery `execute_automation_event` + SLA breach beat

**Re-audit verdict:** COMPLETE — **25/25** Day 6 tests, **33/33** with Day 4/5 regression subset.
