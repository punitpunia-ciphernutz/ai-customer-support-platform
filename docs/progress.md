# Progress — AI Customer Support Platform

Last updated: 2026-09-03 (Teams management + demo roster reseed)

## Status summary

**Day 1–4:** Complete (re-audited 2026-09-01).  
**Day 5:** **Complete** — Email channel, omnichannel foundation, unified inbox.  
**Day 6:** **Complete** — Automation engine, routing, business hours, SLA, notifications, missed chat; audit fixes applied.  
**Teams management:** **Complete** — membership CRUD API + Teams page (assign/remove, edit/delete, membership visibility).

LLM: **Google Gemini** when `GEMINI_API_KEY` is set; otherwise **Echo/heuristic** + offline lexical embeddings.

---

## Teams management (2026-09-03)

| Area | Work |
|------|------|
| API | `GET/PATCH/DELETE /teams/{id}`, membership add/remove, `member_count` + user `teams` enrichment |
| UI | Teams page: member counts, detail modal (edit/add/remove/delete), Teams column on org members |
| Tests | `tests/test_teams_api.py` |

---

## Day 6 — Completed (including audit fix pass)

| Phase | Work |
|-------|------|
| 1 | Migration `0008_day6_automation` + models + seed |
| 2 | `BusinessHoursService` — timezone, holidays |
| 3 | `AssignmentService` — round-robin; ONLINE/AWAY/OFFLINE |
| 4 | `NotificationService` — in-app + email stub + team name resolution |
| 5 | Automation engine — conditions, **16/16 actions**, execution logs, audit |
| 6 | Event bus → automation handler + loop depth contextvar |
| 7 | **SLA wired** — create/priority/reply/close + breach beat job |
| 8 | Missed chat — Celery ETA on conversation create + beat safety net |
| 9 | AI signals; default automations; `intent_team_map` cleared |
| 10 | REST APIs — automations, business-hours, notifications, availability |
| 11 | Frontend — list/create/edit automations, business hours + holidays, execution steps |
| 12 | **25 tests** across 15 files; acceptance (billing, angry, missed chat) |

### Audit fix highlights

- NOTIFY_TEAM resolves team **names** (Route Billing no longer FAILED)
- Manager user + Billing team member seeded
- SLA timers start on billing → HIGH priority path
- Automation create/edit UI at `/automations/new`

## Day 6 tests

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed
docker compose exec backend pytest -q \
  tests/test_day6_phase1_models.py \
  tests/test_day6_conditions.py \
  tests/test_day6_business_hours.py \
  tests/test_day6_assignment_round_robin.py \
  tests/test_day6_acceptance.py \
  tests/test_day6_actions.py \
  tests/test_day6_execution_logs.py \
  tests/test_day6_loop_protection.py \
  tests/test_day6_idempotency.py \
  tests/test_day6_availability.py \
  tests/test_day6_missed_chat_delayed.py \
  tests/test_day6_sla_timers.py \
  tests/test_day6_notifications.py \
  tests/test_day6_event_integration.py \
  tests/test_day6_automation_api.py
```

**Result:** **25/25 passed** (2026-09-02 post-fix)

---

## Documentation

- Day 6 plan: [`docs/day6-implementation-plan.md`](day6-implementation-plan.md)
- Day 6 audit: [`docs/day6-audit.md`](day6-audit.md) — **COMPLETE**
- Day 6 schema: [`docs/database/day6-schema.md`](database/day6-schema.md)
- Run guide: [`docs/run-guide.md`](run-guide.md)

## Default credentials

Shared password for all demo users: **`agent123!`**

| Role | Name | Email | Password | Teams | Use for |
|------|------|-------|----------|-------|---------|
| OWNER | Ava Owner | `owner@example.com` | `agent123!` | — | Full admin / settings |
| ADMIN | Noah Admin | `admin@example.com` | `agent123!` | — | Org admin |
| MANAGER | Maya Manager | `manager@example.com` | `agent123!` | Support | Teams management, escalations, NOTIFY_MANAGER |
| AGENT | Alex Agent | `agent@example.com` | `agent123!` | Support, Billing | Primary inbox agent |
| AGENT | Priya Shah | `priya.support@example.com` | `agent123!` | Support | Round-robin / Team inbox |
| AGENT | Jordan Lee | `jordan.billing@example.com` | `agent123!` | Billing | Billing routing / NOTIFY_TEAM |
| AGENT | Sam Rivera | `sam.both@example.com` | `agent123!` | Support, Billing | Multi-team membership |
| READ_ONLY | Riley Reader | `readonly@example.com` | `agent123!` | — | RBAC 403 checks |

Reseed (cleans junk test users and resets the roster):

```bash
docker compose exec backend python -m app.scripts.seed
```

## Notes

- **Automations:** `/automations`, `/automations/new`, detail + execution steps
- **Business hours:** `/settings/business-hours` — editable schedule + holidays
- **SLA:** timers on conversation create and priority change; breach check via Celery beat
- **Execution logs:** audit trail + `GET /api/v1/automation-executions/:id`
