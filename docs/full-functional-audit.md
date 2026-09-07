# Full Functional Audit — AI Customer Support Platform

**Audit date:** 2026-09-07  
**Scope:** End-to-end product audit (no code changes / no fixes)  
**Environment:** Local Docker Compose (`backend`, `worker`, `beat`, `frontend`, `postgres`, `redis`)  
**Method:** Stack health checks · full backend pytest · frontend `tsc` · live API probes · worker log analysis · code-path review of failing flows  
**Audience:** Manager review / approval before any remediation

---

## Executive verdict

| Area | Status | Notes |
|------|--------|-------|
| Stack health | **PASS** | `/health` healthy (API, DB, Redis, Celery, worker, LLM, storage); frontend HTTP 200 |
| Frontend typecheck | **PASS** | `npm run lint` / `tsc --noEmit` clean |
| Backend automated tests | **FAIL** | **211 passed / 10 failed** (shared-DB + env-sensitive) |
| Auth / RBAC core | **PASS** | Login works; READ_ONLY blocked on writes (403) |
| Knowledge search + AI Test panel | **PASS** | Grounded password-reset answer via `POST /ai/test` |
| Live web-chat AI replies (worker path) | **FAIL (P0)** | Customer messages often get **no AI reply**; worker `skipped` / `MissingGreenlet` |
| Embed widget (seeded ACTIVE) | **PASS (partial)** | Seeded `wgt_4a9Il6Xz5gLxV_67` + domain guard OK historically; dashboard list polluted by test widgets |
| Customers page ticket stats (AGENT) | **FAIL (P1)** | Calls `GET /tickets` without `view` → 403 for agents |
| Auto-assignment suite | **PASS** | `tests/test_auto_assignment.py` **17/17** |
| Widgets / response-policy suites | **PASS** | Related suites **32/32** in targeted run |

**Overall:** Core CRUD, auth, settings APIs, KB search, and sync AI test path work. **Live async AI (the main product path) is unreliable / broken in this environment.** Do not treat the product as manager-demo ready until P0 items below are fixed and re-verified.

---

## What was tested

### Infrastructure
- [x] `docker compose ps` — all 6 services Up
- [x] `GET /health` — all subsystems healthy
- [x] Frontend routes/assets: `/`, `/login`, `/chat`, `/widget-fixture.html`, `/widget.js`, `/widget-frame.html`

### Automated
- [x] Full backend pytest (`docker compose exec backend pytest -q`)
- [x] Frontend TypeScript check
- [x] Targeted: auto-assignment, widgets, response-policy

### Live API (authenticated as agent / owner / manager / readonly)
- [x] Auth login + `/auth/me`
- [x] List endpoints: conversations, customers, teams, automations, knowledge, channels, AI config/runs/usage/evaluations, notifications, business-hours, users, roles, availability
- [x] Customer create / get / 360 / patch
- [x] Public web-chat conversation + messages
- [x] Takeover / return-to-AI / create ticket from conversation
- [x] Email inbound webhook (+ duplicate)
- [x] Knowledge search
- [x] AI Test panel
- [x] Widget admin API (owner) + public domain rejection
- [x] RBAC: readonly create customer → 403
- [x] Tickets with `view=mine|team|unassigned`

### Not fully exercised in this pass (time / long-wait)
- Missed-chat timeout (needs beat wait beyond default minutes)
- Full SLA breach wait
- Email accept-suggestion → outbound send UI click-path
- Full angry-customer + manager notify UI path (partially covered by failing Day 6 tests)
- Every automation action type individually in UI
- PDF knowledge upload UI

---

## Critical / High findings (approve before fixing)

### P0-1 — Live AI worker path fails; customer sees no reply

**Symptom**
- `POST /ai/test` returns a correct grounded answer (`AI_RESOLVE`, `grounded: true`).
- Same question via public web chat leaves **only the customer message** after 12–18s.
- Worker logs show many `process_ai_message` → **`skipped`** in ~40ms, and intermittent:

```text
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
... in AIService._emit_message_received → conv.organization_id
```

**Impact:** Autopilot / Suggest / Knowledge Base on real chats/emails can fail silently (task skipped or rolled back). This breaks the core product demo.

**Likely root causes (code review — not fixed)**
1. **Enqueue before DB commit:** `ConversationService._publish_message` calls `enqueue_ai_message_processing()` while the request session is still uncommitted (`get_db` commits after the response). Worker may load the message before commit → `process_customer_message` returns `None` → `"skipped"`.
2. **MissingGreenlet after successful agent run:** `_emit_message_received` reads `conv.organization_id` after the conversation ORM object may be expired/detached. Exception triggers `session.rollback()` in `_run_process_ai_message`, wiping flushed AI replies / runs.

**Evidence**
- Live probe: conversation `9a3de61c-…` — 1 customer message, 0 AI runs, 0 AI messages; worker `skipped`.
- Worker: multiple `MissingGreenlet` failures around audit traffic.
- Sync path (`/ai/test`) unaffected → LLM + KB retrieval themselves are OK.

**Suggested fix direction (for later approval)**
- Commit (or `flush` + explicit after-commit hook) **before** Celery enqueue; or enqueue from a post-commit callback.
- Capture `organization_id` / IDs as plain values before publish; avoid lazy loads on possibly-expired ORM instances.
- Re-run web-chat password FAQ + OOD soft-refuse after fix.

---

### P0-2 — Intermittent `404 Customer not found` right after create

**Symptom**
- `POST /customers` → 201 with id.
- Immediate `POST /public/conversations` with that id → `404 Customer not found` (seen for OOD / SkipProbe probes).
- Same customers **do exist** in DB seconds later.

**Impact:** `/chat` flow “create customer → paste UUID → start chat” can flake if the second call races the first request’s commit.

**Likely root cause**
- FastAPI `get_db` commits in dependency teardown **after** the response is returned; clients that chain requests immediately can race.

**Suggested fix direction**
- Explicit `await db.commit()` at end of create handlers before return, or document mandatory short delay (not ideal). Prefer commit-before-response for create endpoints used in chained UX.

---

### P1-1 — Customers page ticket counts broken for AGENT

**Where:** `frontend/src/features/customers/CustomersPage.tsx`  
**Call:** `GET /tickets` (default `view=all`)  
**API:** Agents are forbidden from `view=all` → **403** (`Only owners and admins can list all tickets`).

**Impact:** Tickets stat card and per-customer ticket counts stay empty/wrong for the most common role (`agent@example.com`). Page still loads; data is silently incomplete if errors are swallowed by React Query.

**Suggested fix direction**
- Use a permitted view (`team` / combine mine+team+unassigned) or a dedicated aggregate endpoint; match Tickets page behavior.

---

### P1-2 — AI / grounding related pytest failures (env + pipeline)

| Test | Failure | Likely class |
|------|---------|--------------|
| `test_default_factories` | Expects `OfflineSemanticEmbeddingProvider`, gets `GeminiEmbeddingProvider` | Env: `GEMINI_API_KEY` set; test assumes offline default |
| `test_process_customer_message_creates_ai_reply` | No AI message containing “password” | Worker/pipeline / policy / rollback (ties to P0-1) |
| `test_celery_ai_pipeline_publishes_message_event` | `ai_messages == []` | Same |
| `test_draft_only_sends_when_grounded` | Expected `AI_RESOLVE`, got `ESCALATE` | Grounding / retrieval / Gemini vs offline fixtures |
| `test_email_knowledge_base_sends_when_grounded` | No AI email message | Same |

**Note:** These may mix **real pipeline bugs (P0-1)** with **tests that are not hermetic** under Gemini-on.

---

### P1-3 — Day 6 acceptance / seed-order fragile tests

| Test | Failure | Likely class |
|------|---------|--------------|
| `test_day6_billing_message_triggers_automation` | Priority stayed `LOW` not `HIGH` | Automation not firing / classifier / polluted DB automations |
| `test_day6_angry_message_notifies_manager` | (failed in full suite) | Same / notifications |
| `test_notify_team_resolves_team_name` | Notification not found for `User.limit(1)` | First user may not be on Billing team |
| `test_offline_agent_skipped_for_assignment` | `AgentAvailability` missing for `User.limit(1)` | Users without availability rows exist (`readonly@…`, `admin@…`, test users) |
| `test_agent_cannot_write_teams` | `401` vs expected `403` | Auth vs permission assertion drift |

**DB observation:** Many leftover automations from tests (`API Test Automation`, `Toggle Test Automation`, duplicate `Test for angry celery`, etc.). Shared Postgres used by app + pytest increases flakiness.

---

## Medium / Low findings

### P2-1 — Widget list polluted; ACTIVE demo buried
- Seeded ACTIVE widget `wgt_4a9Il6Xz5gLxV_67` (localhost) exists and matches `widget-fixture.html`.
- Dozens of **INACTIVE** test widgets (`Gate Widget`, `Widget A/B`, …) appear first in `GET /widgets`.
- Owner/admin UX: noisy list; easy to open wrong widget during demos.

### P2-2 — Agents cannot manage widgets (by design), but nav still exposes Settings → Chat Widgets
- Widget admin routes require `settings.read` / `settings.write`.
- `AGENT` role does **not** include `SETTINGS_READ` → `GET /widgets` = **403**.
- Settings subnav still lists “Chat Widgets” for all roles that can open Settings pages they can access — confirm UX expectation (hide vs show error).

### P2-3 — Pending knowledge documents stuck
- `documents`: 19 COMPLETED, **2 PENDING** (`Test Doc`).
- May indicate ingestion retries failed or worker skipped; low urgency if demos use completed FAQ docs.

### P2-4 — Deprecation warning
- `datetime.utcnow()` in notifications routes (pytest warning). Non-blocking.

### P2-5 — False “failures” in naive HTTP audits
- Public conversation create returns **201** (correct); scripts expecting 200 will mis-report.
- Agent `GET /tickets` without view → 403 is **intended RBAC**, not an API bug (but Customers UI must respect it — see P1-1).

---

## What is working (confirmed)

| Feature | Result |
|---------|--------|
| Health / worker / beat up | OK |
| Login (agent, manager, owner, readonly) | OK |
| Inbox conversation list | OK |
| Customers CRUD + 360 | OK (create race caveat P0-2) |
| Teams list + members | OK |
| Automations list + executions list | OK |
| Channels get WEB_CHAT / EMAIL | OK (enabled) |
| Business hours list | OK |
| Notifications list | OK |
| Agent availability PATCH ONLINE | OK |
| Takeover / return-to-AI API | OK |
| Create ticket from conversation | OK (201) |
| Email inbound webhook + idempotent duplicate | OK |
| Knowledge search (password reset) | OK (3 hits ~0.71) |
| AI Test panel grounded resolve | OK |
| Widget domain reject (`evil.com`) | OK (403) historically / design |
| Auto-assignment unit/integration suite | OK 17/17 |
| Frontend TypeScript | OK |
| READ_ONLY write blocked | OK |

---

## Feature matrix (manual checklist status from this audit)

| ID | Area | Result |
|----|------|--------|
| TC-01 Stack healthy | PASS | |
| TC-02 Worker alive + AI test | PASS (test panel) / **FAIL live chat** | |
| TC-KB search | PASS | |
| TC-WC Autopilot WITH KB | **FAIL** (no customer AI message) | |
| TC-WC OOD / soft refuse | **BLOCKED** (create race / no AI) | |
| TC-WC Takeover API | PASS | |
| TC-EM inbound + duplicate | PASS | |
| TC-EM Suggest appears | **INCONCLUSIVE** (probe cut short; depends on P0-1) | |
| TC-EW fixture widget id | PASS (seeded id present) | |
| TC-EW domain guard | PASS | |
| TC-IN tickets views | PASS with `view=` | |
| TC-IN Customers ticket stats | **FAIL** for AGENT | |
| TC-AU auto-assign tests | PASS (automated) | |
| TC-CH channels/settings APIs | PASS | |

---

## Test suite snapshot

```text
Full pytest (shared DB):  211 passed, 10 failed
Auto-assignment:          17 passed
Widgets + response policy (+ related): 32 passed
Frontend tsc:             passed
```

Failing files (full suite):
- `tests/test_chunk_embed.py`
- `tests/test_day3_agent.py` (2)
- `tests/test_day4_modes.py`
- `tests/test_day5_email_knowledge_base.py`
- `tests/test_day6_acceptance.py` (1–2)
- `tests/test_day6_actions.py`
- `tests/test_day6_availability.py`
- `tests/test_teams_api.py`

---

## Risk summary for management

1. **Demo risk is high** if the script is: open `/chat` → ask FAQ → expect AI reply. Sync Settings → AI Test works; **real chat often does not**.
2. **Root issues look fixable** (commit/enqueue ordering + ORM expire on event emit) without redesigning the agent.
3. **Test suite is not a clean gate** on this shared database + Gemini-on config; green CI needs hermetic DB and provider mocks.
4. **UI RBAC mismatch** on Customers tickets will confuse agents during UAT.

---

## Recommended next steps (awaiting your approval)

**Do not implement until approved.** Suggested order:

1. **Approve fix for P0-1** (AI enqueue-after-commit + MissingGreenlet in `_emit_message_received`) — highest priority.
2. **Approve fix for P0-2** (customer create commit-before-return / chained public chat).
3. **Approve fix for P1-1** (CustomersPage tickets query).
4. Re-run this audit’s live matrix (web chat WITH/WITHOUT KB, email suggest, widget fixture, angry/billing).
5. Separately: clean test hermeticity (embedding factory, `User.limit(1)` seed assumptions) and prune orphan test widgets/automations in non-prod DB.

---

## Sign-off

| Role | Name | Decision | Date |
|------|------|----------|------|
| Manager | | ☐ Approve fixes · ☐ Defer · ☐ Need more QA | |
| Engineer | | Audit only — no code changed | 2026-09-07 |

**Related docs:** [`manual-test-scenarios.md`](manual-test-scenarios.md) · [`run-guide.md`](run-guide.md) · [`auto-assignment-plan.md`](auto-assignment-plan.md) · prior day audits in `docs/day*-audit.md`
