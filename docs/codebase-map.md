# Codebase Map — AI Customer Support Platform

Use this doc when you need to change something and want to know **which folder/file to open**.

**Related docs**

| Doc | Purpose |
|-----|---------|
| [run-guide.md](run-guide.md) | How to run / demo |
| [progress.md](progress.md) | What’s done (Day 1/2) |
| [day1-day2-final-audit.md](day1-day2-final-audit.md) | Spec compliance |

---

## 1. Big picture

```
Browser (React)
    │  REST  /api/v1/*
    │  WS    /ws  (agents)  ·  /ws/public  (web chat)
    ▼
FastAPI (backend/app)
    ├── Auth / RBAC
    ├── Support core: customers, conversations, tickets, teams
    ├── Knowledge: ingest → chunk → embed → pgvector → search
    └── AI: classify via LangGraph (no auto-reply yet)
    │
    ├── PostgreSQL (+ pgvector)
    ├── Redis (events pub/sub + Celery broker)
    └── Celery worker (knowledge ingestion jobs)
```

| Layer | Lives in | Responsibility |
|-------|----------|----------------|
| UI | `frontend/src/` | Pages, forms, realtime inbox/chat |
| HTTP/WS API | `backend/app/modules/*/router.py` or `api/routes.py` | Validate request, auth, call services |
| Business logic | `*/service.py`, `*/application/` | Domain rules, orchestration |
| Persistence models | `infrastructure/database/models.py` + knowledge/ai domain models | Tables / ORM |
| Background jobs | `backend/app/workers/` | Celery tasks (ingest) |
| Infra glue | `backend/app/infrastructure/` | DB session, events, audit, logging |
| Config | `backend/app/config/settings.py` + `.env` | Env vars |

---

## 2. Repository root

```
AI Customer Support Platform/
├── backend/              # FastAPI + Celery + Alembic
├── frontend/             # React + Vite + TypeScript
├── docs/                 # Plans, audits, this map
├── docker-compose.yml    # postgres, redis, backend, worker, frontend
├── Makefile              # make up / down / migrate / test / logs
├── .env.example          # Env template (copy to .env)
└── README.md
```

| Want to… | Change |
|----------|--------|
| Add a Docker service | `docker-compose.yml` |
| Change default ports / env for Compose | `docker-compose.yml` + `.env` |
| Add a make shortcut | `Makefile` |
| Change shared env defaults | `.env.example` (and local `.env`) |

---

## 3. Backend map

### 3.1 Top-level backend layout

```
backend/
├── app/                  # Application code (import as `app.*`)
├── migrations/           # Alembic DB migrations
├── tests/                # pytest
├── scripts/              # DB init SQL (pgvector)
├── pyproject.toml        # Python deps
├── Dockerfile
├── alembic.ini
└── .env.example
```

### 3.2 App entry & wiring

| Path | What it does | Change here when… |
|------|----------------|-------------------|
| `app/main.py` | Creates FastAPI app: CORS, request IDs, OTel, exception handler, mounts `/api/v1` + WebSockets | Changing middleware, global error handling, app startup |
| `app/api/router.py` | Aggregates all module routers under `/api/v1` | Registering a **new API module** |
| `app/api/deps.py` | `get_current_user`, `require_permission(...)` | Auth dependency behavior, permission checks |
| `app/config/settings.py` | Pydantic settings from env (`GEMINI_API_KEY`, DB URLs, chunk size, etc.) | New config knobs / defaults |

**Request path example**

```
POST /api/v1/customers
  → main.py (middleware)
  → api/router.py
  → modules/customers/router.py
  → require_permission(...)
  → DB via get_db()
```

### 3.3 Shared infrastructure

```
app/infrastructure/
├── database/
│   ├── base.py          # SQLAlchemy DeclarativeBase
│   ├── session.py       # async engine, get_db(), commit/rollback
│   └── models.py        # Core Day-1 tables (org, user, customer, conversation, …)
├── events/
│   └── bus.py           # DomainEvent + Redis pub/sub
├── audit.py             # write_audit(...)
├── logging.py           # structured logs + request_id context
└── redis/               # placeholder package
```

| Path | What it does | Change here when… |
|------|----------------|-------------------|
| `database/models.py` | Organization, User, Role, Team, Customer, Conversation, Message, Ticket, AuditLog, enums | Changing **core** schema (then add Alembic migration) |
| `database/session.py` | DB connection / session lifecycle | Connection URL usage, commit behavior |
| `events/bus.py` | Publish events → Redis channel `support.events` | New event payload shape / channel name |
| `audit.py` | Inserts `audit_logs` rows | Audit field shape or helper API |
| `logging.py` | Log format + binding request/correlation IDs | Logging format |

### 3.4 Modules (feature packages)

Each business area lives under `app/modules/<name>/`.

#### Auth — `modules/auth/`

| File | Role |
|------|------|
| `router.py` | `POST /auth/login`, `/logout`, `GET /auth/me` |
| `security.py` | Password hash, JWT create/decode |
| `permissions.py` | Permission strings + role → permissions map |
| `schemas.py` | Login / token / user response models |

**Change here for:** login behavior, JWT expiry claims, adding a permission, role permission matrix.

#### Customers — `modules/customers/`

| File | Role |
|------|------|
| `router.py` | CRUD `/customers` |
| `schemas.py` | Request/response Pydantic models |

**Change here for:** customer fields, list filters, customer API validation.

#### Conversations / messages — `modules/conversations/`

| File | Role |
|------|------|
| `router.py` | Thin HTTP: agent + **public** web-chat endpoints |
| `service.py` | **ConversationService** — create/update/list, messages, events, audit |
| `channels.py` | `ChannelAdapter` + WebChat/Email/Form adapters |
| `schemas.py` | Conversation/message DTOs |

**Important flows**

- Agent inbox message → `router` → `ConversationService.add_agent_message` → adapter → DB → Redis event  
- Customer web chat → `/public/conversations...` → same service (no agent JWT)

**Change here for:** conversation status rules, assign/close logic, new channel adapter, public chat API.

#### Tickets — `modules/tickets/`

| File | Role |
|------|------|
| `router.py` | Ticket CRUD + `view=mine\|team\|all\|unassigned` + team ACL |
| `schemas.py` | Ticket DTOs |

#### Teams — `modules/teams/`

| File | Role |
|------|------|
| `router.py` | Team CRUD + membership |
| `schemas.py` | Team / member DTOs |
| `service.py` | Membership, unique name, delete guards |
| `access.py` | Shared team membership + ticket visibility helpers |

#### Users — `modules/users/`

| File | Role |
|------|------|
| `router.py` | `GET/POST/PATCH /users`, `GET /roles`, password reset |
| `schemas.py` | User list (role + teams), create/update DTOs |
| `service.py` | Hierarchy guards, audit (`user.created`, `user.role_changed`) |

#### Notifications — `modules/notifications/`

| File | Role |
|------|------|
| `api/routes.py` | List, mark read, **read-all**, preferences |
| `application/service.py` | `notify` / `notify_team` / `notify_managers` |

#### Inbox realtime — `modules/inbox/`

| File | Role |
|------|------|
| `ws.py` | WebSocket `/ws` (JWT required) and `/ws/public`; Redis → broadcast |

**Change here for:** WS auth rules, which clients get which events.

#### Knowledge — `modules/knowledge/` (Day 2)

```
knowledge/
├── api/routes.py                 # HTTP: sources, documents, search
├── domain/
│   ├── models.py                 # KnowledgeSource, Document, DocumentChunk (pgvector)
│   └── schemas.py                # API schemas
├── application/
│   ├── knowledge_service.py      # Source/document CRUD queries
│   └── ingestion_service.py      # normalize → hash → chunk → embed → store
└── infrastructure/
    ├── loaders/base.py           # TEXT / PDF / URL loaders
    ├── parsers/
    │   ├── chunker.py            # Chunker (LangChain splitter)
    │   └── normalize.py          # text normalize, content_hash, html_to_text
    ├── embeddings/provider.py    # EmbeddingProvider: Gemini + offline lexical
    ├── langchain/adapters.py     # LangChain Embeddings + BaseRetriever wrappers
    └── vectorstore/retriever.py  # PgVectorRetriever (public API free of LangChain types)
```

| Want to… | Open |
|----------|------|
| Add knowledge API endpoint | `api/routes.py` |
| Change Source/Document/Chunk columns | `domain/models.py` + new Alembic migration |
| Change ingest pipeline | `application/ingestion_service.py` |
| Support a new file type | `infrastructure/loaders/` |
| Change chunk size/overlap defaults | `config/settings.py` (`CHUNK_*`) + `parsers/chunker.py` |
| Change embedding model/provider | `infrastructure/embeddings/provider.py` + settings |
| Change search ranking / top_k | `vectorstore/retriever.py` + settings `KNOWLEDGE_TOP_K` |

#### AI — `modules/ai/` (Day 2)

```
ai/
├── api/routes.py                 # POST /ai/classify
├── application/ai_service.py     # classify/generate/summarize + AIRun persistence
├── domain/
│   ├── interfaces.py             # LLM / Embedding / Retriever / AgentRuntime ABCs
│   ├── models.py                 # AIRun ORM
│   └── schemas.py                # AIClassification, intents, request/response
├── graphs/
│   ├── classification.py         # LangGraph: receive → context → classify
│   └── minimal.py                # Day-1 smoke graph
└── infrastructure/llm/providers.py  # GeminiLLMProvider + EchoLLMProvider
```

| Want to… | Open |
|----------|------|
| Change classify API | `api/routes.py` |
| Persist more AIRun fields | `domain/models.py` + migration |
| Change intents / classification schema | `domain/schemas.py` |
| Change LangGraph steps | `graphs/classification.py` |
| Change Gemini model / prompts | Settings → AI Support → Model (`ai_configs.llm_model`); prompts in `infrastructure/llm/providers.py` + env `LLM_MODEL` default |
| Wire AI into chat auto-reply | **Don’t** — that’s Day 3; keep boundary via `AIService` |

#### Placeholders (empty for later)

| Folder | Future use |
|--------|------------|
| `modules/automation/` | Playbooks / automation builder |
| `modules/integrations/` | Slack, WhatsApp, HubSpot, etc. |
| `modules/organization/`, `users/`, `messages/` | Optional homes for logic currently elsewhere |

### 3.5 Workers (Celery)

| Path | Role |
|------|------|
| `app/workers/celery_app.py` | Celery app + broker config |
| `app/workers/tasks.py` | `ingest_document` job + `hello_world`; PDF upload dir helper |

**Change here for:** new background jobs, ingest job retries, upload directory.

Flow:

```
POST /knowledge/.../documents/*  (returns 202)
  → ingest_document.delay(document_id)
  → worker: load TEXT/PDF/URL → IngestionService → chunks + embeddings
```

### 3.6 Migrations & seed

| Path | Role |
|------|------|
| `migrations/versions/0001_initial.py` | Core support tables + pgvector extension |
| `migrations/versions/0002_knowledge.py` | Knowledge tables |
| `migrations/versions/0003_ai_runs.py` | `ai_runs` |
| `app/scripts/seed.py` | Seeds org, roles, demo agent, default team |
| `scripts/init-pgvector.sql` | `CREATE EXTENSION vector` on first Postgres boot |

**Never edit old migrations that may already be applied** — add a new `0004_*.py` instead.

### 3.7 Tests

| File | Focus |
|------|-------|
| `test_health.py` | Health endpoints |
| `test_api_smoke.py` | Login → customer → conversation (needs running API) |
| `test_channel_adapter.py` | WebChat adapter |
| `test_day1_day2_gaps.py` | RBAC, audit, WS auth, no auto-reply |
| `test_knowledge_models.py` | KB models / routes present |
| `test_chunk_embed.py` | Chunker + embeddings |
| `test_ingestion_loaders.py` | Loaders + ingest |
| `test_celery_ingest.py` | Celery ingest pipeline |
| `test_semantic_search.py` | Multi-doc ranking + LangChain adapter |
| `test_search_and_classify.py` | Search + AIRun |
| `test_ai_graph.py` | LangGraph classify |
| `test_gemini_provider.py` | Gemini/Echo wiring (no live API) |

---

## 4. Frontend map

### 4.1 Layout

```
frontend/
├── src/
│   ├── main.tsx              # React mount
│   ├── styles.css            # Global theme / CSS variables
│   ├── app/
│   │   ├── App.tsx           # Renders router
│   │   ├── router.tsx        # All routes + auth gate
│   │   └── providers.tsx     # QueryClient + BrowserRouter + AuthProvider
│   ├── features/             # One folder per product area (pages)
│   ├── components/
│   │   ├── shared/AppShell.tsx   # Sidebar nav layout
│   │   └── ui/                   # Shared primitives (skeleton)
│   ├── services/api/client.ts    # fetch wrapper + JWT
│   ├── hooks/useSupportSocket.ts # WebSocket helper
│   ├── types/index.ts            # Shared TS types
│   └── utils/cn.ts               # Small className helper
├── package.json
├── vite.config.ts            # `@/` → `src/`
└── Dockerfile
```

### 4.2 Routes → pages

Defined in `src/app/router.tsx`:

| URL | Page file | Auth? |
|-----|-----------|-------|
| `/login` | `features/auth/LoginPage.tsx` | No |
| `/chat` | `features/conversations/WebChatPage.tsx` | No (customer chat) |
| `/` | `features/inbox/InboxPage.tsx` | Yes |
| `/customers` | `features/customers/CustomersPage.tsx` | Yes |
| `/knowledge` | `features/knowledge/KnowledgePage.tsx` | Yes |
| `/knowledge/:sourceId` | same file (`KnowledgeSourcePage`) | Yes |
| `/tickets` | `features/tickets/TicketsPage.tsx` | Yes |
| `/teams` | `features/teams/TeamsPage.tsx` | Yes |
| `/settings` | `features/settings/SettingsPage.tsx` | Yes (placeholder) |

Nav links live in `components/shared/AppShell.tsx`.

### 4.3 Feature folders (what each UI owns)

| Folder | Responsibility | Talks to |
|--------|----------------|----------|
| `features/auth/` | Login form; `AuthContext` holds user + token | `/auth/login`, `/auth/me`, `/auth/logout` |
| `features/inbox/` | Agent inbox: Team/Mine filters, thread, reply, assign | `/conversations`, `/messages`, `/users`, `/teams` + WS |
| `features/notifications/` | AppShell notification bell | `/notifications` + WS |
| `features/customers/` | Create/list customers | `/customers` |
| `features/conversations/` | Customer-facing web chat | `/public/conversations...` + `/ws/public` |
| `features/knowledge/` | Sources list, add TEXT/PDF/URL, status, delete | `/knowledge/...` |
| `features/tickets|settings/` | Placeholders for later UI | (APIs exist on backend) |
| `features/teams/` | Teams + org user admin (roles, invite-with-temp-password, deactivate) | `/teams`, `/users`, `/roles` |

### 4.4 Shared frontend utilities

| File | Role | Change when… |
|------|------|----------------|
| `services/api/client.ts` | `api()` helper, token storage, `API_BASE` | Auth header rules, base URL, error handling |
| `hooks/useSupportSocket.ts` | Connects agent WS or public WS | WS URL / reconnect logic |
| `types/index.ts` | `User`, `Customer`, `Conversation`, `Message` | Shared response shapes |
| `styles.css` | Colors, fonts, layout tokens | Global look & feel |
| `app/providers.tsx` | React Query + Router + Auth | Global providers |

### 4.5 Env (frontend)

| Variable | Meaning |
|----------|---------|
| `VITE_API_BASE_URL` | e.g. `http://localhost:8000/api/v1` |
| `VITE_WS_BASE_URL` | e.g. `ws://localhost:8000/ws` |

Set in root `.env` / `frontend/.env.example`. Compose bakes them in at **frontend image build** time.

---

## 5. End-to-end flows (where code runs)

### A. Agent login → inbox reply

1. `LoginPage` → `POST /auth/login` (`auth/router.py`)  
2. Token saved (`client.ts` / `AuthContext`)  
3. `InboxPage` loads `/conversations` (`conversations/service.py`)  
4. `useSupportSocket` opens `/ws?token=…` (`inbox/ws.py`)  
5. Reply → `POST .../messages` → `ConversationService` → Redis event → WS refresh  

### B. Customer web chat

1. Create customer in UI → copy UUID  
2. `/chat` → `POST /public/conversations` (+ messages)  
3. Public WS `/ws/public` for live updates  
4. Agent sees same conversation in inbox  

### C. Knowledge ingest → search

1. Knowledge UI → create source → add document  
2. API returns **202** → Celery `ingest_document` (`workers/tasks.py`)  
3. Loader → chunk → embed → `document_chunks.embedding`  
4. `POST /knowledge/search` → `PgVectorRetriever` (LangChain under the hood)  

### D. AI classify (not wired into chat)

1. `POST /ai/classify`  
2. `AIService` → LangGraph → Gemini/Echo → save `AIRun`  
3. **Does not** post a customer message (by design for Day 2)

---

## 6. “I want to change X” cheat sheet

| Goal | Start here |
|------|------------|
| Add a REST endpoint | Module `router.py` / `api/routes.py` → register in `app/api/router.py` if new module |
| Add a DB column (core) | `infrastructure/database/models.py` + new Alembic migration |
| Add a DB column (knowledge) | `knowledge/domain/models.py` + migration |
| Add a DB column (AI runs) | `ai/domain/models.py` + migration |
| Change permissions | `auth/permissions.py` + re-seed (`make seed`) |
| Change login / JWT | `auth/security.py`, `auth/router.py`, `config/settings.py` |
| Change conversation rules | `conversations/service.py` |
| Add WhatsApp/email channel | New adapter in `conversations/channels.py` + wire in service |
| Change inbox UI | `frontend/.../inbox/InboxPage.tsx` |
| Change web chat UI | `frontend/.../conversations/WebChatPage.tsx` |
| Change knowledge UI | `frontend/.../knowledge/KnowledgePage.tsx` |
| Change embedding model | `embeddings/provider.py` + `EMBEDDING_MODEL` in `.env` |
| Change LLM model | `llm/providers.py` + `LLM_MODEL` in `.env` |
| Change classify graph | `ai/graphs/classification.py` |
| Change background ingest | `workers/tasks.py` + `ingestion_service.py` |
| Change realtime fan-out | `infrastructure/events/bus.py` + `inbox/ws.py` |
| Add frontend route | `app/router.tsx` + new page under `features/` + link in `AppShell` |
| Add Python dependency | `backend/pyproject.toml` then rebuild Docker images |
| Add frontend dependency | `frontend/package.json` then rebuild frontend |

---

## 7. Conventions to keep

1. **Routers stay thin** — business logic in services (`ConversationService`, `KnowledgeService`, `AIService`).  
2. **Don’t call LangGraph/LangChain from conversation routers** — go through `AIService` / knowledge interfaces.  
3. **Org scoping** — almost every query filters by `organization_id` from the current user.  
4. **Migrations are additive** — never rewrite applied revisions.  
5. **Secrets** — only in `.env` (never commit). Examples live in `.env.example`.  
6. **Day 3 boundary** — grounded auto-replies / agent tools are not in this codebase yet; add them via `AIService` + conversation service, not by sprinkling LLM calls in the UI.

---

## 8. Quick mental model

```
frontend/features/<name>     → UI for that feature
backend/app/modules/<name>   → API + logic for that feature
backend/app/infrastructure   → shared DB / events / audit
backend/app/workers          → async jobs
backend/migrations           → schema history
```

If you’re unsure where to edit: find the **URL or screen** first → match it in §4.2 (frontend) or the module router (backend) → follow into the **service** / **page** file listed above.
