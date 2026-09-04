# Embeddable Chat Widget — Implementation Plan

**Goal:** Turn the existing Web Chat channel into a Tawk.to-style embeddable chatbot that clients install on their own websites via a copyable JavaScript snippet, while reusing the current Conversation / Message / AI / Ticket / Inbox pipeline unchanged.

**Principle:** The widget is a **delivery surface** for `ChannelType.WEB_CHAT`. Conversations remain the core. AI operates on conversations, not on widgets. Do not build a second chat or AI system.

**Rule:** Extend Days 1–6 architecture (`ConversationService`, public chat APIs, `WebChatAdapter`, LangGraph support agent, response policy, Celery, event bus, inbox). Add widget identity, visitor sessions, domain security, and an embeddable UI. Keep `/chat` for internal testing/debugging.

**Depends on:** Existing public Web Chat (`POST/GET /public/conversations…`), AI pipeline, response policy, escalation/tickets, per-channel `BotConfiguration`, `ChannelConfiguration` for `WEB_CHAT`.

**Status:** PLAN ONLY — not implemented.

---

## 1. Executive summary

| Capability | Today | After this work |
|------------|--------|-----------------|
| Public chat UI | Full-page `/chat` (paste Customer UUID) | Floating bubble on client sites + keep `/chat` |
| Tenant resolution | From pre-created `Customer.organization_id` | From **Widget ID** → organization |
| Visitor identity | Manual customer UUID paste | Auto create/restore visitor session |
| Install method | None | Copyable `<script>` embed snippet |
| Domain security | Global CORS env list only | Per-widget allowed domains + Origin checks |
| Branding | Soft AI display name only | Per-widget colors, position, welcome, offline |
| Realtime | Open `/ws/public` fans out all events | Conversation-scoped public WS (or token-gated) |
| AI / tickets / takeover | Working end-to-end | Unchanged path: same services |

---

## 2. What already exists (reuse)

### 2.1 Web Chat surface

| Piece | Path | Notes |
|-------|------|--------|
| Full-page chat UI | `frontend/src/features/conversations/WebChatPage.tsx` | Requires customer UUID; stores IDs in `localStorage` |
| Message bubbles | `frontend/src/features/conversations/MessageBubble.tsx` | Reusable for widget panel |
| Chat helpers | `frontend/src/features/conversations/chatUtils.ts` | Pending-message helpers |
| Public socket hook | `frontend/src/hooks/useSupportSocket.ts` | Agent `/ws` vs public `/ws/public` |
| AI wait / timeout UX | `frontend/src/hooks/useAwaitingAiResponse.ts` | Polls `check-ai-response` |
| Route | `/chat` in `frontend/src/app/router.tsx` | Standalone, no AppShell — **keep** |

### 2.2 Public chat APIs (unauthenticated today)

| Method | Path | Behavior |
|--------|------|----------|
| `POST` | `/api/v1/public/conversations` | Create `WEB_CHAT` conversation for **existing** `customer_id` |
| `POST` | `/api/v1/public/conversations/{id}/messages` | Customer message (`customer_id` + `content`) |
| `GET` | `/api/v1/public/conversations/{id}/messages?customer_id=` | Non-internal messages |
| `POST` | `/api/v1/public/conversations/{id}/check-ai-response` | AI timeout → escalate/ticket |

Source: `backend/app/modules/conversations/router.py` → `ConversationService`.

### 2.3 Message → AI → response path (do not fork)

```
Visitor message
  → ConversationService.add_public_message / create_public_conversation
  → Redis message.created
  → Celery process_ai_message
  → AIService.process_customer_message
  → run_support_agent (LangGraph)
       classify → response_policy → retrieve → generate → confidence → escalate
  → side effects by AIMode (AUTO_REPLY / SUGGEST / DRAFT_ONLY)
  → WS fan-out → client refreshes messages
```

| Layer | Path |
|-------|------|
| Orchestration | `backend/app/modules/conversations/service.py` |
| Adapter | `backend/app/modules/conversations/channels.py` (`WebChatAdapter`) |
| AI enqueue | `backend/app/modules/ai/tasks_bridge.py` |
| Worker | `backend/app/workers/tasks.py` |
| AI service | `backend/app/modules/ai/application/ai_service.py` |
| Graph | `backend/app/modules/ai/graphs/support_agent.py` |
| Policy | `backend/app/modules/ai/application/response_policy.py` |
| Escalation | `backend/app/modules/ai/application/escalation_service.py` |

### 2.4 Customers, channels, AI config, agents

| Piece | Exists | Gap for widget |
|-------|--------|----------------|
| `Customer` (+ `external_id`, `metadata`) | Yes | No anonymous visitor create from public API |
| `CustomerResolver.resolve_by_email` | Yes (email channel) | Need visitor / widget external_id resolve |
| `ChannelConfiguration` (`enabled`, `settings` JSON) | Yes | No widget-specific fields; WEB_CHAT `enabled` **not enforced** on public chat |
| `BotConfiguration` per channel | Yes | Reuse WEB_CHAT mode; optional per-widget override later |
| `AIConfig` + response policy | Yes | Reuse as-is |
| Inbox / takeover / tickets | Yes | Conversations already appear as `WEB_CHAT` |
| Multi-org schema (`organization_id`) | Yes | Public APIs do not take widget/org key |
| Auth JWT helpers | Yes (`create_access_token` / `decode_access_token`) | No visitor token type yet |
| CORS | Global `Settings.cors_origins` | Not dynamic per client domain |

### 2.5 Explicitly missing (must add)

- Widget entity + unique public Widget ID
- Dashboard CRUD + embed snippet + preview + install docs
- Embed loader script + floating bubble/panel package
- Allowed-domains validation
- Automatic visitor session create/restore
- Secure public auth (visitor/session token) instead of raw customer UUID as sole gate
- Conversation-scoped public WebSocket
- Enforcement of WEB_CHAT channel enabled for embed traffic

---

## 3. Target architecture

```
Client website (allowed domain)
  │
  │  <script src="…/widget.js" data-widget-id="wgt_xxx">
  ▼
Embed loader
  ├── Domain preflight (Origin / page host)
  ├── Inject launcher bubble
  └── Open chat panel (iframe recommended)
        │
        │  REST + WS (visitor token)
        ▼
Public Widget API  (/api/v1/public/widgets/…)
  ├── Resolve widget_id → organization + config
  ├── Validate Origin against allowed_domains
  ├── Create/restore visitor Customer + session token
  └── Delegate to ConversationService (WEB_CHAT)
        │
        ▼
Existing conversation core
  ├── Messages / participants / SLA / missed-chat
  ├── AI pipeline (unchanged)
  ├── Escalation → Ticket
  ├── Human takeover / return-to-AI
  └── Events → Redis → scoped WS → widget + agent inbox
```

**Non-goals for v1**

- New `ChannelType` (keep `WEB_CHAT`)
- Separate AI graph or reply pipeline
- Multi-language widget SDK packages beyond JS
- WhatsApp / other channels
- Full SaaS org provisioning UI (schema already multi-org; one org per install is fine)
- Replacing `/chat` internal test page

---

## 4. Design decisions (recommended)

### 4.1 Widget ≠ new channel

**Decision:** Store widgets as first-class rows under an organization. All embed conversations still use `channel=WEB_CHAT`.

**Why:** Inbox filters, bot modes, missed-chat, escalation, and tests already key off `WEB_CHAT`. Avoid dual pipelines.

Optional later: `conversations.metadata.widget_id` or nullable `widget_id` FK for analytics/filtering without changing channel enum.

### 4.2 Embed packaging: loader + iframe

**Decision:** Ship a small `widget.js` loader that injects a floating bubble and mounts the chat UI in an **iframe** served by our frontend (or static CDN path).

**Why:** CSS/JS isolation from host sites; simpler security (token stays in iframe origin); matches Tawk/Intercom patterns.

Alternative (v1.5): Shadow DOM single-bundle — more host-CSS leakage risk; defer unless iframe is blocked by CSP on target sites.

### 4.3 Visitor identity

**Decision:**

1. On first open, call `POST /public/widgets/{widget_id}/session` with optional name/email.
2. Backend creates or restores a `Customer` in the widget’s org:
   - With email → `CustomerResolver.resolve_by_email`
   - Anonymous → `Customer` with name `"Visitor"` (or generated) and `external_id = "widget:{widget_id}:vid:{visitor_key}"`
3. Issue a short-lived **visitor JWT** (`typ=visitor`, claims: `org_id`, `widget_id`, `customer_id`, optional `conversation_id`).
4. Widget stores `visitor_key` (stable UUID) + token in `localStorage` keyed by widget ID.

**Do not** require agents to pre-create customers. Keep existing public endpoints working for `/chat` testing (backward compatible), but embed traffic should use the new widget session APIs.

### 4.4 Domain validation

**Decision:** Each widget has `allowed_domains: string[]` (e.g. `example.com`, `www.example.com`, `*.staging.example.com`).

On every public widget request:

1. Read `Origin` (preferred) or `Referer`.
2. Normalize host (lowercase, strip port for standard ports, reject IPs unless explicitly allowed).
3. Match against allowlist (exact or single-level wildcard prefix).
4. Reject with `403` if missing/mismatch when allowlist is non-empty.
5. For local dashboard preview, allow `localhost` / configured preview origins via a `preview=true` path that requires agent JWT instead of domain check.

Also: dynamic CORS for widget API routes — reflect validated Origin only (do not open `*` globally).

### 4.5 Public WebSocket hardening (required for multi-client)

**Decision:** Replace open fan-out for embed clients:

- `WS /ws/public?token=<visitor_jwt>`  
  or  
- `WS /ws/widget?token=<visitor_jwt>`

Server accepts connection, binds to `organization_id` + `conversation_id` (subscribe list), and only forwards events for those conversations.

Keep agent `/ws` as-is (optionally later scope by org from JWT).

`/chat` internal page should migrate to the same token-scoped socket once visitor sessions exist for test customers, or continue polling-only until Phase 3.

### 4.6 Configuration ownership

| Setting | Where |
|---------|--------|
| Widget appearance, welcome, status, domains, snippet | New `chat_widgets` table |
| Channel on/off for WEB_CHAT | Existing `ChannelConfiguration` — **enforce** for embed |
| AI mode / thresholds | Existing `AIConfig` + `BotConfiguration(WEB_CHAT)` |
| Soft branding strings | Existing AI response-policy fields; widget welcome message is separate |

Avoid stuffing all widget UI config into `ChannelConfiguration.settings` once multiple widgets per org are required — a dedicated table is clearer.

---

## 5. Database changes / migrations

**Suggested migration:** `0011_chat_widgets.py` (next after `0010_response_policy`).

### 5.1 New table: `chat_widgets`

| Column | Type | Notes |
|--------|------|--------|
| `id` | UUID PK | Internal ID |
| `organization_id` | UUID FK → organizations | Indexed |
| `public_id` | String(32–64) UNIQUE | Public Widget ID for embed (`wgt_…`) — **not** the PK |
| `name` | String(255) | Dashboard label |
| `status` | Enum/string | `ACTIVE` \| `INACTIVE` \| `DRAFT` |
| `allowed_domains` | JSONB | `["example.com", "*.example.com"]` |
| `appearance` | JSONB | Colors, position, launcher text, avatar URL, z-index |
| `welcome_message` | Text | Shown before/at first message |
| `offline_message` | Text nullable | When inactive or outside hours (optional v1) |
| `require_email` | Bool default false | Pre-chat form |
| `require_name` | Bool default false | Pre-chat form |
| `ai_settings` | JSONB nullable | Optional thin overrides; default = inherit WEB_CHAT bot config |
| `created_at` / `updated_at` | timestamptz | |

Indexes:

- `uq_chat_widgets_public_id` on `public_id`
- `ix_chat_widgets_org` on `organization_id`

### 5.2 Optional but recommended: `conversations.widget_id`

| Column | Type | Notes |
|--------|------|--------|
| `widget_id` | UUID FK → chat_widgets NULL | Set for embed-originated chats; null for legacy `/chat` |

Enables inbox filter “by widget” and isolation audits without new channel type.

### 5.3 Optional: visitor key on customer metadata

Prefer `Customer.external_id` for stable anonymous visitors:

```
widget:{public_id}:vid:{visitor_uuid}
```

Unique constraint consideration: add partial unique index on `(organization_id, external_id)` where `external_id IS NOT NULL` if not already present.

### 5.4 Docs to update after migration

Per project workflow, add/update:

- `docs/database/chat-widgets-schema.md` — table purpose, columns, relations, access patterns
- Brief note in `docs/codebase-map.md` under channels / frontend

### 5.5 What not to change

- Do not alter historical migrations `0001`–`0010`
- Do not fork `messages`, `ai_runs`, `tickets`, or `bot_configurations` schemas for widgets
- Do not add a parallel `widget_messages` table

---

## 6. Backend changes

### 6.1 New module layout

```
backend/app/modules/widgets/
  ├── __init__.py
  ├── models.py          # or add ChatWidget to infrastructure/database/models.py (match repo style)
  ├── schemas.py
  ├── service.py         # CRUD, domain validation, session bootstrap
  ├── domain_guard.py    # Origin / host matching
  ├── visitor_token.py   # issue/verify visitor JWT (reuse jose helpers)
  ├── router.py          # agent dashboard APIs
  └── public_router.py   # public embed APIs
```

Register in `backend/app/api/router.py`.

### 6.2 Agent (dashboard) APIs

Auth: JWT + `settings.read` / `settings.write` (reuse existing permissions).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/widgets` | List widgets for org |
| `POST` | `/api/v1/widgets` | Create widget (generates `public_id`) |
| `GET` | `/api/v1/widgets/{id}` | Detail + embed snippet payload |
| `PATCH` | `/api/v1/widgets/{id}` | Update appearance, domains, status, messages |
| `DELETE` | `/api/v1/widgets/{id}` | Soft-delete or hard-delete if unused |
| `GET` | `/api/v1/widgets/{id}/embed-snippet` | Returns copyable HTML/JS string |
| `POST` | `/api/v1/widgets/{id}/preview-token` | Short-lived preview session for dashboard iframe |

### 6.3 Public (embed) APIs

No agent JWT. Require valid Widget ID + domain check + (after bootstrap) visitor token.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/public/widgets/{public_id}/config` | Public config for UI (appearance, welcome, status). **No secrets.** Domain-validated. |
| `POST` | `/api/v1/public/widgets/{public_id}/session` | Create/restore visitor + issue visitor JWT |
| `POST` | `/api/v1/public/widgets/{public_id}/conversations` | Start conversation (delegates to `ConversationService`) |
| `POST` | `/api/v1/public/widgets/{public_id}/conversations/{id}/messages` | Send message |
| `GET` | `/api/v1/public/widgets/{public_id}/conversations/{id}/messages` | List visible messages |
| `POST` | `/api/v1/public/widgets/{public_id}/conversations/{id}/check-ai-response` | Reuse timeout service |

Implementation pattern:

```python
# pseudo
widget = await WidgetService.get_by_public_id(public_id)
assert_widget_active(widget)
assert_domain_allowed(request, widget.allowed_domains)
assert_web_chat_channel_enabled(widget.organization_id)
visitor = verify_visitor_token(...)  # except on /session + /config
# then call ConversationService.create_public_conversation / add_public_message
```

**Important:** Public widget message handlers must call the **same** `ConversationService` methods used today so Celery AI enqueue, events, missed-chat, and tickets stay identical.

### 6.4 Legacy public APIs

Keep:

- `POST /public/conversations`
- `POST/GET /public/conversations/{id}/messages`
- `POST /public/conversations/{id}/check-ai-response`

These power `/chat` for debugging. Optionally:

- Add soft warning in docs that they are internal/test
- Later require a feature flag or restrict to non-production
- Do **not** remove in v1 (would break tests and manual scenarios)

### 6.5 ConversationService touchpoints (minimal)

| Change | Why |
|--------|-----|
| Accept optional `widget_id` when creating from embed | Persist FK / metadata |
| Enforce `ChannelConfiguration.enabled` for `WEB_CHAT` on public create/message | Parity with email webhook gate |
| Optionally tag message metadata `{"source": "embed", "widget_public_id": "…"}` | Debugging / analytics |

Avoid rewriting `_create_from_incoming` or AI side effects.

### 6.6 CustomerResolver extensions

Add:

- `resolve_anonymous_visitor(organization_id, external_id, name=…)`
- Reuse `resolve_by_email` when pre-chat email provided

### 6.7 Visitor token

Reuse `create_access_token` / `decode_access_token` with extra claims:

```json
{
  "sub": "<customer_id>",
  "typ": "visitor",
  "org_id": "...",
  "widget_id": "<internal or public>",
  "conversation_id": "<optional>"
}
```

Shorter TTL than agent tokens (e.g. 24h) + refresh via `/session`. Reject tokens where `typ != visitor` on widget routes.

### 6.8 Domain guard

`domain_guard.py` responsibilities:

- Parse Origin/Referer host
- Normalize (`www` optional matching policy — document choice: **exact match only** unless wildcard entry present)
- Support `*.example.com` (suffix match, no multi-label surprise)
- Unit-test extensively (open redirect / spoofed Origin cases)

### 6.9 CORS

Options (pick one in Phase 2):

1. **Middleware extension:** For paths under `/api/v1/public/widgets/`, if Origin matches widget allowlist, echo `Access-Control-Allow-Origin: <origin>` + credentials/headers as needed.
2. **Iframe-only:** Host widget UI on our origin; only loader on client site — API calls same-origin from iframe → simpler CORS (recommended with iframe approach).

With iframe hosted on our domain, browser Origin for API calls is **our** frontend origin; domain validation then uses a `page_origin` / `parent_host` field sent by the widget (and verified against `Referer` of the parent via `postMessage` handshake). Document this clearly in implementation — **parent hostname must be attested**, not trusted blindly from JS alone.

**Recommended attestation flow:**

1. Loader on client site posts `{type:"WIDGET_INIT", host: location.hostname}` into iframe via `postMessage`.
2. Iframe includes `X-Widget-Page-Host: example.com` on API calls.
3. Backend validates header against allowlist **and** optional signed loader handshake token issued at config fetch time bound to that host.

Keep it as simple as possible while preventing trivial spoofing from curl without knowing an allowlisted host (defense in depth: widget must be ACTIVE + host allowlisted + visitor token).

### 6.10 WebSocket changes

File: `backend/app/modules/inbox/ws.py`

| Today | Target |
|-------|--------|
| `/ws/public` accepts anyone, broadcasts all Redis events | Token-required; filter by conversation/org |
| Single global public connection list | Map `conversation_id → [websockets]` |

Event payload already includes conversation identifiers on `message.created` — use those for routing. Agents keep receiving via `/ws` (consider org filter as follow-up if multi-tenant noise becomes an issue).

### 6.11 Seed / scripts

- Seed one default widget for the demo org with `allowed_domains=["localhost"]`
- Document Widget ID in `docs/run-guide.md`

---

## 7. Frontend / widget changes

### 7.1 Dashboard (authenticated app)

New feature area:

```
frontend/src/features/widgets/
  ├── WidgetsPage.tsx           # list
  ├── WidgetDetailPage.tsx      # config, snippet, preview, install steps
  ├── WidgetForm.tsx            # appearance, domains, welcome, status
  ├── EmbedSnippetCard.tsx      # copyable snippet
  ├── WidgetPreview.tsx         # live preview iframe
  └── types.ts
```

Routing (`router.tsx`):

- `/widgets` — list
- `/widgets/new` — create
- `/widgets/:widgetId` — detail / install

Nav: add under Settings or top-level “Chat Widgets” in `AppShell` (prefer Settings sub-nav + Channels sibling for cohesion).

Reuse existing UI primitives (`PageHeader`, `Alert`, tables, forms) — do not invent a new design system.

### 7.2 Widget runtime package

Two viable repo layouts:

**A (recommended for monorepo simplicity):**  
`frontend/src/widget/` + separate Vite entry `widget.html` / `widget.ts` built to `dist/widget/` and served as static assets.

**B:** `packages/chat-widget/` workspace — only if packaging/CDN needs diverge strongly.

Build outputs:

| Artifact | Role |
|----------|------|
| `widget.js` (loader) | Client pastes this; reads `data-widget-id`; injects bubble + iframe |
| `widget-frame.js` + CSS | Chat UI inside iframe |
| Optional `widget.css` | Launcher styles for host page (minimal) |

Snippet shape (illustrative):

```html
<!-- Support Platform Chat -->
<script
  async
  src="https://<APP_HOST>/widget.js"
  data-widget-id="wgt_abc123"
></script>
```

### 7.3 Widget UI behavior

1. Load public config → apply colors/position/welcome  
2. If `INACTIVE`, show offline message or hide launcher (configurable)  
3. Session bootstrap on first open  
4. Optional pre-chat form (name/email) when required  
5. Conversation create on first message (same as today’s WebChatPage flow)  
6. Realtime via scoped WS; fallback to existing `useAwaitingAiResponse` polling  
7. Hide internal/suggestion messages (reuse `metadata.internal` filter)  
8. Show ticket-created notice (reuse existing copy patterns)

**Reuse:** Extract shared chat panel logic from `WebChatPage` into a small shared module used by both `/chat` and the iframe app — avoid maintaining two message lists forever. Keep `/chat` entry for UUID-based debugging **or** add a “debug mode” toggle; simplest is keep UUID flow on `/chat` untouched in Phase 1 and extract shared components in Phase 3.

### 7.4 Preview in dashboard

- Iframe pointing at widget frame URL with `preview_token`  
- Or embedded React preview using the same components with mock/live session against localhost allowlist  
- Show installation steps: copy snippet → paste before `</body>` → add domain → verify bubble

### 7.5 Keep internal Web Chat

- Do not remove `/chat` or its sidebar “open in new tab” link  
- Label it “Internal Web Chat (test)” in UI copy if helpful  
- Manual test scenarios for public API remain valid

---

## 8. Security

| Threat | Mitigation |
|--------|------------|
| Widget used on unauthorized site | `allowed_domains` + host attestation |
| Customer UUID guessing (legacy) | New embed path uses visitor JWT; rate-limit public APIs; consider deprecating raw UUID gate later |
| Cross-tenant data leak via `/ws/public` | Conversation-scoped WS + visitor token |
| Config endpoint leaking secrets | Public config returns only presentation fields |
| Spam / abuse | Rate limit by IP + widget_id; optional CAPTCHA later |
| XSS from welcome message | Treat as text; sanitize if HTML ever allowed (v1: plain text only) |
| Disabled channel still reachable | Enforce `ChannelConfiguration.enabled` for WEB_CHAT |
| Inactive widget | Reject session/message with 403 |
| Token theft from localStorage | Short TTL; bind token to widget_id + customer_id; HTTPS only |

**Out of scope for v1 (document as follow-ups):** CAPTCHA, WAF rules, per-IP ban lists, signed CSP nonces for loader.

---

## 9. Visitor / session flow

```
1. Host page loads widget.js (data-widget-id=wgt_X)
2. Loader checks page host locally (UX only) → opens iframe
3. Iframe: GET /public/widgets/wgt_X/config  (+ page host header)
4. If status != ACTIVE → show offline / hide
5. On launcher click:
   a. Read localStorage[sp_widget_wgt_X] → { visitor_key, token, conversation_id? }
   b. POST /session { visitor_key?, name?, email? }
   c. Store returned { visitor_token, customer_id, visitor_key }
6. User sends first message:
   POST .../conversations { content }  → Conversation (WEB_CHAT, widget_id set)
7. Subsequent messages:
   POST .../conversations/{id}/messages
8. AI / agent / ticket path unchanged
9. On return visit: restore visitor_key → same customer; reopen or continue conversation policy:
   - Default: resume last OPEN conversation for that customer+widget if recent
   - Else create new conversation on next message
```

**Conversation resume policy (v1 recommendation):** Resume last non-closed conversation for `(customer_id, widget_id)` within N days (configurable, default 7); otherwise start fresh. Store `conversation_id` in localStorage as cache only — server is source of truth.

---

## 10. Configuration model (appearance & AI)

### 10.1 Appearance JSON (suggested shape)

```json
{
  "primary_color": "#0F766E",
  "text_color": "#FFFFFF",
  "launcher_position": "bottom-right",
  "launcher_text": "Chat with us",
  "border_radius_px": 16,
  "z_index": 999999,
  "logo_url": null
}
```

Keep fields minimal; avoid a design studio in v1.

### 10.2 AI settings

**v1:** Inherit org `AIConfig` + `BotConfiguration` for `WEB_CHAT`. Widget UI may link to Channel Settings (“AI mode is configured under Channels → Web Chat”).

**v1.1 (optional):** `ai_settings.mode` override per widget written into metadata for analytics only, or a thin override table — only if product requires different modes per site. Prefer not to in v1.

### 10.3 Status

| Status | Behavior |
|--------|----------|
| `DRAFT` | Dashboard only; public config 404/403 |
| `ACTIVE` | Embed works on allowlisted domains |
| `INACTIVE` | Config may load; messaging rejected; launcher shows offline message |

---

## 11. Tenant / widget isolation checklist

- [ ] Every widget row scoped by `organization_id`
- [ ] Public APIs resolve org **only** via widget `public_id`, never from client-supplied org id
- [ ] Visitor tokens include `org_id` + `widget_id`; mismatch → 401
- [ ] Conversations created with widget’s `organization_id` and customer in same org
- [ ] Message list endpoints verify conversation belongs to visitor’s customer + org
- [ ] Agent APIs continue filtering by `user.organization_id`
- [ ] WS delivers only subscribed conversation events
- [ ] Domains cannot be empty in production for ACTIVE widgets (allow empty only for DRAFT)

---

## 12. Testing strategy

### 12.1 Backend unit / API tests (new)

| Area | Cases |
|------|--------|
| Domain guard | exact match, wildcard, port strip, evil.com vs example.com, missing Origin |
| Widget CRUD | create generates public_id; patch domains; inactive rejects |
| Session | anonymous create; email resolve; restore by visitor_key; token claims |
| Messaging | message → same Celery enqueue path (mock); AI disabled / human control still respected |
| Isolation | widget A token cannot read widget B / other org conversation |
| Channel gate | WEB_CHAT disabled → 403 on embed create |
| Legacy public API | existing tests still pass unchanged |

### 12.2 Regression

Run existing suites that touch public chat / AI / escalation:

- Day 3/4 AI agent tests
- Response policy tests
- Day 5 channel / webhook enabled patterns (mirror for WEB_CHAT)
- Manual scenarios in `docs/manual-test-scenarios.md` § public webchat — keep green

### 12.3 Frontend

- Lint/typecheck widget + dashboard pages
- Manual: paste snippet into a static HTML fixture served on allowlisted host
- Preview iframe in dashboard
- Confirm `/chat` still works with seeded customer UUID

### 12.4 Security smoke

- Curl message API with wrong Origin / host → 403  
- Connect WS without token → reject  
- Token for conv A subscribed but event for conv B → not delivered  

### 12.5 Do not require

- Full production build in exploratory PR work unless asked  
- E2E Playwright suite in v1 (nice-to-have follow-up)

---

## 13. Rollout steps

1. **Migrate DB** (`0011_chat_widgets`) on staging  
2. Deploy backend with widget APIs; feature flag optional (`WIDGETS_ENABLED`)  
3. Seed demo widget; verify public config + session on localhost  
4. Deploy frontend dashboard pages + static `widget.js` assets  
5. Harden WS (deploy carefully — coordinate `/chat` clients)  
6. Internal dogfood: embed on staging marketing page  
7. Enforce WEB_CHAT `enabled` gate (confirm seed leaves it enabled)  
8. Document install in `docs/run-guide.md` + in-app instructions  
9. Production enable; monitor 403 domain mismatches and WS errors  
10. Only then consider tightening/deprecating legacy UUID public chat  

**Rollback:** Feature-flag off embed routes; widgets unused; legacy `/chat` unaffected. Migration is additive — safe to leave tables in place.

---

## 14. Phased implementation order

### Phase 0 — Spec lock (½ day)

- Confirm iframe vs shadow DOM  
- Confirm visitor JWT TTL and resume policy  
- Confirm empty allowlist policy for ACTIVE widgets  

### Phase 1 — Data model + agent APIs (1–2 days)

1. Alembic migration `chat_widgets` (+ optional `conversations.widget_id`)  
2. ORM model + schemas  
3. `WidgetService` CRUD + `public_id` generation  
4. Agent routes under `/api/v1/widgets`  
5. Schema doc `docs/database/chat-widgets-schema.md`  
6. Seed default widget  
7. API tests for CRUD  

**Exit:** Agents can create a widget via API; DB populated.

### Phase 2 — Public session + domain security (2–3 days)

1. `domain_guard.py` + unit tests  
2. Visitor token helpers  
3. `CustomerResolver` anonymous path  
4. Public config + session endpoints  
5. Public conversation/message endpoints wrapping `ConversationService`  
6. Enforce WEB_CHAT channel enabled  
7. CORS / page-host attestation for chosen embed model  
8. Isolation tests  

**Exit:** curl/Postman can simulate embed session → message → existing AI path fires.

### Phase 3 — Realtime hardening (1–2 days)

1. Scoped `/ws/public` or `/ws/widget` with visitor JWT  
2. Update `useSupportSocket` for token mode  
3. Regression on agent inbox WS  
4. Fallback polling remains via `check-ai-response`  

**Exit:** No cross-conversation event leakage on public socket.

### Phase 4 — Embed UI package (2–3 days)

1. Vite multi-entry build for `widget.js` + frame  
2. Launcher bubble + panel UI (reuse MessageBubble patterns)  
3. Session/localStorage wiring  
4. Welcome / offline / pre-chat form  
5. Static HTML fixture for local install test  

**Exit:** Snippet on fixture site opens chat and completes a round-trip with AI.

### Phase 5 — Dashboard UX (1–2 days)

1. Widgets list/detail pages  
2. Appearance + domains + status forms  
3. Copyable embed snippet  
4. Live preview  
5. Install instructions panel  
6. Nav + Settings integration  
7. Keep `/chat` labeled for testing  

**Exit:** Non-engineer can create widget, copy snippet, configure domains.

### Phase 6 — Polish, docs, hardening (1 day)

1. Rate limiting on public widget routes  
2. Update `docs/run-guide.md`, `docs/codebase-map.md`, manual test scenarios  
3. Logging/metrics: widget_id on conversation create  
4. Final regression pass  

---

## 15. File change map (expected)

### Backend (add/modify)

| Path | Action |
|------|--------|
| `backend/migrations/versions/0011_chat_widgets.py` | Add |
| `backend/app/infrastructure/database/models.py` | Add `ChatWidget`; optional `Conversation.widget_id` |
| `backend/app/modules/widgets/**` | Add module |
| `backend/app/api/router.py` | Register routers |
| `backend/app/modules/conversations/service.py` | Minimal: widget_id, enabled gate |
| `backend/app/modules/customers/resolver.py` | Anonymous visitor resolve |
| `backend/app/modules/inbox/ws.py` | Scope public WS |
| `backend/app/main.py` | Optional CORS tweak |
| `backend/app/scripts/seed.py` | Seed widget |
| `backend/tests/test_widgets_*.py` | Add |

### Frontend (add/modify)

| Path | Action |
|------|--------|
| `frontend/src/features/widgets/**` | Dashboard UI |
| `frontend/src/widget/**` (+ vite config entries) | Embed runtime |
| `frontend/src/app/router.tsx` | Widget routes |
| `frontend/src/components/shared/AppShell.tsx` | Nav link |
| `frontend/src/hooks/useSupportSocket.ts` | Visitor token support |
| `frontend/src/features/conversations/WebChatPage.tsx` | Keep; optional shared extract later |

### Docs

| Path | Action |
|------|--------|
| `docs/embeddable-chat-widget-plan.md` | This plan |
| `docs/database/chat-widgets-schema.md` | Add with migration |
| `docs/run-guide.md` | Install/demo steps |
| `docs/codebase-map.md` | Index new module |
| `docs/manual-test-scenarios.md` | Embed scenarios section |

### Explicitly do not touch (unless bugfix)

- `support_agent.py` graph topology  
- Response policy core logic  
- Knowledge/RAG pipeline  
- Email adapter / webhooks  
- Automation engine  

---

## 16. API contract sketches

### `GET /api/v1/public/widgets/{public_id}/config`

Response:

```json
{
  "public_id": "wgt_abc123",
  "name": "Marketing site",
  "status": "ACTIVE",
  "welcome_message": "Hi! How can we help?",
  "offline_message": "We're offline right now.",
  "require_name": false,
  "require_email": false,
  "appearance": { "primary_color": "#0F766E", "launcher_position": "bottom-right" }
}
```

### `POST /api/v1/public/widgets/{public_id}/session`

Request:

```json
{
  "visitor_key": "optional-uuid",
  "name": "optional",
  "email": "optional@example.com",
  "page_url": "https://example.com/pricing",
  "page_host": "example.com"
}
```

Response:

```json
{
  "visitor_key": "…",
  "customer_id": "…",
  "visitor_token": "…",
  "expires_at": "…"
}
```

### Embed conversation create

Request (Authorization: `Bearer <visitor_token>`):

```json
{ "content": "I need help with billing", "metadata": { "page_url": "…" } }
```

Internally: `ConversationService` create with `channel=WEB_CHAT`, `customer_id` from token, `widget_id` set → existing AI enqueue.

---

## 17. Success criteria (Definition of Done)

- [ ] Client can create a Chat Widget in the dashboard and receive a unique Widget ID  
- [ ] Dashboard shows a copyable embed snippet and installation instructions  
- [ ] Pasting the snippet on an allowlisted site shows the chat bubble  
- [ ] Disallowed domains cannot start sessions or send messages  
- [ ] Visitors are auto-created/restored without pasting customer UUIDs  
- [ ] Messages flow through existing Conversation → AI → Ticket / takeover path  
- [ ] Multiple widgets/orgs cannot read each other’s conversations  
- [ ] Appearance, welcome message, status, allowed domains configurable  
- [ ] Widget preview works in dashboard  
- [ ] Internal `/chat` remains available for testing  
- [ ] Existing backend tests remain green; new widget tests cover domain + isolation  
- [ ] Schema documentation updated for new tables/columns  

---

## 18. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Scope creep into “second chat system” | Hard rule: only wrap `ConversationService` |
| Breaking `/ws/public` for demo `/chat` | Phase WS carefully; support dual mode briefly |
| CORS complexity on third-party sites | Prefer iframe hosted on our origin |
| Anonymous customer spam | Rate limits; optional require_email |
| Multi-widget AI confusion | v1 inherits WEB_CHAT bot config only |
| Host CSP blocking iframe/script | Document CSP requirements (`script-src`, `frame-src`) in install guide |

---

## 19. Estimated effort

| Phase | Effort |
|-------|--------|
| 0 Spec lock | 0.5 d |
| 1 Data + agent API | 1–2 d |
| 2 Public session + domains | 2–3 d |
| 3 WS hardening | 1–2 d |
| 4 Embed UI | 2–3 d |
| 5 Dashboard UX | 1–2 d |
| 6 Polish + docs | 1 d |
| **Total** | **~9–13 engineering days** |

---

## 20. Open questions (resolve in Phase 0)

1. Should ACTIVE widgets require at least one allowed domain? (**Recommend: yes**)  
2. Resume last conversation vs always-new on each visit? (**Recommend: resume OPEN within 7 days**)  
3. Serve `widget.js` from the Vite frontend container vs backend static mount? (**Recommend: frontend/CDN**)  
4. Soft-delete widgets vs hard delete when conversations exist? (**Recommend: soft status INACTIVE + block delete if conversations reference widget**)  
5. Do we need per-widget AI mode in v1? (**Recommend: no**)  

---

## Appendix A — Current message flow (reference)

```
WebChatPage / Widget
  → POST /public/.../messages
  → ConversationService.add_public_message
  → _publish_message (Redis)
  → enqueue_ai_message_processing
  → Celery process_ai_message
  → AIService.process_customer_message
  → run_support_agent
  → AUTO_REPLY message or SUGGEST internal or escalate→Ticket
  → WS event → UI refresh
```

Embed work inserts **before** `ConversationService` (identity, domain, widget resolve) and **around** delivery (bubble UI, scoped WS). Everything from `ConversationService` downward stays shared.

## Appendix B — Related docs

- `docs/codebase-map.md` — module index  
- `docs/day5-implementation-plan.md` — channel adapter principle  
- `docs/response-policy-implementation-plan.md` — AI reply policy  
- `docs/manual-test-scenarios.md` — public webchat scenarios  
- `docs/database/day5-schema.md` — `channel_configurations`  
- `docs/day6-implementation-plan.md` — notes Help Center / chat widget as deferred  
