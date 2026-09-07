# Progress — AI Customer Support Platform

Last updated: 2026-09-07

## Status summary

| Area | Status |
|------|--------|
| Day 1–4 (core, KB, AI agent, reliability) | Complete |
| Day 5 (email, omnichannel, attachments) | Complete |
| Day 6 (automations, SLA, notifications, missed chat) | Complete |
| Teams + user admin RBAC | Complete |
| Notifications UI + team-scoped tickets | Complete |
| Auto-assignment (round-robin / ensure assignee) | Complete |
| Response policy (soft greetings / OOD / no-KB) | Complete |
| Embeddable chat widgets | Complete |
| Attachment HTTP download (inbox) | Complete |

LLM: **Google Gemini** when `GEMINI_API_KEY` is set; otherwise **Echo/heuristic** + offline lexical embeddings.

---

## Recent (2026-09-07)

### Attachment download

- `GET /api/v1/attachments/{id}/download` streams file bytes (auth required).
- Inbox attachment chips fetch with bearer token (no `file://` links).
- Docker Compose volume `attachment_uploads` → `/tmp/support-attachments` so blobs survive container restarts.

### Embeddable widgets

- Settings → Chat Widgets; seeded Demo Website Widget (`localhost` allowlisted).
- Visitor identity in browser `localStorage` (`sp_widget_<public_id>`) — per visitor, not per website.
- Fixture: http://localhost:5173/widget-fixture.html

### Response policy (Settings → AI)

- Soft-reply greetings/identity skip KB (canned intro).
- Soft-refuse when OOD / no relevant KB (unless escalate toggles say otherwise).
- `require_knowledge` applies to support questions that reach retrieval — not to soft greeting replies.

---

## Feature highlights

| Area | Notes |
|------|-------|
| Inbox | Unified WEB_CHAT + EMAIL; takeover / return-to-AI |
| Knowledge | Sources, PDF/URL ingest, hybrid retrieval + grounding |
| Email | Mock inbound webhook; outbound send; attachments stored + downloadable |
| Automations | Conditions/actions, billing routing, execution logs |
| Business hours / SLA | Settings UI; beat jobs for breach + missed chat |
| Teams / users | Membership CRUD; hierarchy-guarded user admin |

---

## Default credentials

Shared password: **`agent123!`**

| Role | Name | Email | Teams |
|------|------|-------|-------|
| OWNER | Ava Owner | `owner@example.com` | — |
| ADMIN | Noah Admin | `admin@example.com` | — |
| MANAGER | Maya Manager | `manager@example.com` | Support |
| AGENT | Alex Agent | `agent@example.com` | Support, Billing |
| AGENT | Priya Shah | `priya.support@example.com` | Support |
| AGENT | Jordan Lee | `jordan.billing@example.com` | Billing |
| AGENT | Sam Rivera | `sam.both@example.com` | Support, Billing |
| READ_ONLY | Riley Reader | `readonly@example.com` | — |

```bash
docker compose exec backend python -m app.scripts.seed
```

---

## Documentation (current)

| Doc | Purpose |
|-----|---------|
| [run-guide.md](run-guide.md) | Run / demo |
| [manual-test-scenarios.md](manual-test-scenarios.md) | Manual QA |
| [codebase-map.md](codebase-map.md) | Code navigation |
| [database/](database/) | Schema references |

Historical day-by-day plans and audits were removed; schema + run/test docs are the source of truth.
