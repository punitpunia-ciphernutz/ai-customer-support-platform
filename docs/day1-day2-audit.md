# Day 1 + Day 2 Audit — AI Customer Support Platform

**Audit date:** 2026-08-27  
**Sources of truth:** `AI Customer Support.docx` (Day 1), `AI Customer Support (1).docx` (Day 2)  
**Scope:** Read-only verification of repository state. No code was modified for this audit.

**Status legend**

| Status | Meaning |
|--------|---------|
| COMPLETE | Requirement implemented as specified |
| PARTIALLY COMPLETE | Present but incomplete, shallow, or not wired end-to-end |
| MISSING | Not found |
| INCORRECT | Present but contradicts the spec / architecture / intended behavior |

---

## Executive verdict

Day 1 **Support Core** is largely in place and demoable (auth → customers → web chat → inbox → realtime → assign/close → audit). Day 2 **Knowledge + AI foundations** are structurally present (models, Celery ingestion, search API, LangGraph classification, AIRun, Knowledge UI), but two foundations the Day 3 agent depends on are weak:

1. **Embeddings are hash-local, not semantic** — Flow A “relevant knowledge” is not reliably demonstrated.
2. **LangChain is a dependency only** — never imported or used in application code.

**The project is not fully ready to start Day 3** until retrieval quality and LangChain boundaries are fixed (or consciously deferred with an explicit Day-3 risk).

---

# Day 1 — Support Platform Core

## 1. Repository setup

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Monorepo with `backend/`, `frontend/`, `docker-compose.yml`, `.gitignore`, `README.md`, `Makefile` | COMPLETE | Layout matches spec | — | — |
| Backend modules under `app/` (`api/`, `modules/*`, `infrastructure/*`, `workers/`, `config/`) | PARTIALLY COMPLETE | Core modules exist; `automation/`, `integrations/` are empty placeholders | `organization/`, `users/`, `messages/` are empty shells; logic lives in other routers | Keep placeholders or move thin routers into those modules for clarity |
| Frontend feature-based `src/` | PARTIALLY COMPLETE | `app/`, `features/{auth,inbox,conversations,customers,knowledge}`, `components/shared`, `services/api`, `hooks`, `types` | Missing `features/tickets`, `features/teams`, `features/settings`, `components/ui`, `utils/`; `app/router.tsx` is empty (routes live in `App.tsx`) | Add skeleton feature folders; move routes into `router.tsx` per Day 1 layout |
| Stack: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, Postgres, Redis, Celery, pytest, React/TS/Vite/RQ/RHF/Zod | COMPLETE | Matches `pyproject.toml` / `package.json` | — | — |

## 2. Docker environment

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Compose services: frontend, backend, postgres, redis, worker | COMPLETE | `docker-compose.yml` | — | — |
| PostgreSQL with pgvector (no separate vector DB) | COMPLETE | `pgvector/pgvector:pg16` + `CREATE EXTENSION vector` in init SQL and migration `0001` | — | — |
| `docker compose up` starts full env | COMPLETE | Backend migrates + seeds; worker + frontend depend on backend | — | Document that frontend serves built assets on `:5173→80` in Compose |

## 3. FastAPI foundation

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| `GET /health`, `GET /api/v1/health` → `{status: ok}` | COMPLETE | `main.py`, `api/router.py` | — | — |
| CORS, env config, structured logging, exception handling, API versioning, OpenAPI, DB + auth deps | PARTIALLY COMPLETE | CORS + pydantic-settings; OpenAPI; `get_db`; `get_current_user` / `require_permission`; global exception handler; request/correlation IDs | Logging format includes `request_id` but middleware does not bind it into log records; OTel TracerProvider set without FastAPI instrumentation/exporter | Wire request context into logging; instrument FastAPI or document OTel as stub-only |

## 4. Database foundation

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| SQLAlchemy 2 + Alembic + Postgres | COMPLETE | Models + `0001_initial` | — | — |
| Entities: Organization, User, Role, Team, TeamMember, Customer, Conversation, Message, Ticket, AuditLog | COMPLETE | `infrastructure/database/models.py` | Extra `Participant`, `subject` on Conversation (compatible) | — |
| Relationships org → users/teams/customers/conversations → messages | COMPLETE | ORM relationships defined | — | — |

## 5. Single-tenant organization model

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| One Organization with id, name, domain, timezone, logo_url, settings, timestamps | COMPLETE | Model + seed “Acme Support” | No org CRUD API (not required by Day 1 API list) | — |
| No TenantResolver / TenantDatabase / TenantConnectionPool | COMPLETE | Not present | — | — |
| Entities carry `organization_id` | COMPLETE | Scoped queries use org id | — | — |

## 6. Authentication

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | COMPLETE | JWT access token; logout is no-op (client discard) | Stateless logout is acceptable for Day 1 | Optionally add token denylist later |
| Password auth + secure hashing + current-user dep | COMPLETE | passlib/bcrypt + Bearer JWT | — | — |
| No SSO/OAuth/MFA | COMPLETE | Not built | — | — |

## 7. RBAC

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Roles OWNER, ADMIN, MANAGER, AGENT, READ_ONLY | COMPLETE | `RoleName` enum + seed | — | — |
| Permission catalog (customers/conversations/tickets/users/teams/settings) | COMPLETE | `permissions.py` | Day 2 also added `knowledge.*` (correct) | — |
| Reusable authz dependency (not inline role checks) | COMPLETE | `require_permission(...)` | Assign check in conversation PATCH is a second permission gate (acceptable) | — |

## 8. Customer domain

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| CRUD: GET list, GET by id, POST, PATCH | COMPLETE | `customers/router.py` | — | — |
| Model fields per spec | COMPLETE | Including `metadata` | — | — |
| No full Customer 360 | COMPLETE | Basic CRUD only | — | — |

## 9–10. Conversation + Message

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Conversation model (channel, status, priority, assignees, etc.) | COMPLETE | Enums WEB_CHAT/EMAIL/FORM; OPEN/PENDING/CLOSED; LOW…URGENT | — | — |
| Message model with sender_type including AI | COMPLETE | CUSTOMER/AGENT/AI/SYSTEM | — | — |
| Participant entity | COMPLETE | `participants` table | — | — |
| Conversation APIs (list/create/get/patch + messages) | COMPLETE | Plus public web-chat endpoints | — | — |
| Application `ConversationService` (architecture diagram) | MISSING | Logic lives in FastAPI routers | Spec diagrams show ConversationService between adapters and persistence | Extract service layer before Day 3 wiring |

## 11. Channel architecture

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| `ChannelAdapter` with receive/send/normalize/identify_customer | PARTIALLY COMPLETE | ABC + WebChat/Email/Form adapters in `channels.py` | Adapters are barely used (`get_adapter` only validates channel on create); Email/Form raise `NotImplementedError`; message path does not go IncomingMessage → service | Wire create/message flows through adapter.normalize; keep Email/Form as stubs |
| Normalized `IncomingMessage` | PARTIALLY COMPLETE | Dataclass exists | Not used by routers | Use in public + agent message entry |

## 12. Web Chat (minimum)

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Customer React chat → POST conversation/messages → WS → inbox | COMPLETE | `/chat` + public APIs + agent inbox | UX requires pasting customer UUID (acceptable for Day 1) | Optional polish: pick customer from list |
| No AI replies / chatbot personality | COMPLETE | No AI in chat path | — | — |

## 13. WebSocket layer

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Events: message.created, conversation.updated/assigned/closed | COMPLETE | Published via Redis pub/sub → WS broadcast | — | — |
| Flow Postgres → Event → Redis → WS → React | COMPLETE | `EventBus` + `inbox/ws.py` + `useSupportSocket` | Soft auth: WS allows connections without token | Require JWT for agent inbox socket; keep public chat on separate channel if needed |

## 14. Inbox UI

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Views: All / Mine / Unassigned / Team | COMPLETE | Query `view=` + UI filters | — | — |
| Open, reply, assign, change priority, close, reopen | PARTIALLY COMPLETE | Reply, assign user, priority, close/reopen | No explicit status control for `PENDING`; no team assign control in UI | Add status + team assignee controls |

## 15. React architecture / libraries

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| TanStack Query, React Router, RHF, Zod | PARTIALLY COMPLETE | Used on login/customers; Query on inbox/knowledge | Knowledge/inbox forms mostly uncontrolled; empty `router.tsx` | Align structure with Day 1 tree; use RHF/Zod on knowledge forms optionally |

## 16. Ticket foundation

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Ticket model separate from Conversation | COMPLETE | Statuses OPEN…CLOSED; resolved_at/closed_at | — | — |
| Ticket APIs GET/POST/GET id/PATCH | COMPLETE | `tickets/router.py` | No tickets UI (not required for Day 1 demo) | Day 3+ optional UI |
| Escalation abstraction only (basic) | COMPLETE | Manual ticket create API | — | — |

## 17. Event system

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Domain events for customer/conversation/message/ticket | PARTIALLY COMPLETE | Most events published | No dedicated subscribers beyond WS fan-out; AI future events not defined as constants | Add event name constants; optional in-process handlers |
| Bridge for future AI events | PARTIALLY COMPLETE | Bus is reusable | No `ai.*` event types yet (Day 2+ OK) | Emit `ai.run.*` when classification runs (Day 3 prep) |

## 18. Audit logging

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| AuditLog model | COMPLETE | Matches spec fields | — | — |
| Track conversation.assigned/closed, ticket.created/assigned, customer.updated, user.role_changed | PARTIALLY COMPLETE | assigned/closed/created/customer.updated/ticket.assigned written | `user.role_changed` never written (no role-change API); `ticket.resolved` emits event but no audit row | Add role-change API later or drop from checklist; write audit on ticket resolve |

## 19–20. AI foundation (Day 1 prepare only)

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Interfaces: LLMProvider, EmbeddingProvider, Retriever, AIService, AgentRuntime | PARTIALLY COMPLETE | `AgentRuntime` stub; concrete LLM/Embedding/Retriever/AIService exist (mostly Day 2) | Day 1 wanted interface boundaries under `ai/domain/interfaces.py` — only AgentRuntime remains there | Consolidate interface ABCs in `domain/interfaces.py` |
| Minimal LangGraph START→Input→Model→Output→END | COMPLETE | `graphs/minimal.py` | — | — |
| AI not in customer conversation flow (Day 1) | COMPLETE | Classify is separate `/ai/classify` | — | — |
| LangChain/LangGraph deps installed | PARTIALLY COMPLETE | Both in `pyproject.toml`; LangGraph used | LangChain never imported (Day 1 “foundation” OK; Day 2 requires usage) | See Day 2 LangChain section |

## 21. pgvector (Day 1)

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Enable pgvector; do not build full ingestion on Day 1 | COMPLETE | Extension enabled in Day 1 migration; full pipeline is Day 2 | — | — |

## 22. Redis + Celery

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Celery configured; Day 1 proves a job runs | COMPLETE | `hello_world` task + Day 2 `ingest_document` | — | — |

## 23. Observability foundation

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Structured logs, request ID, correlation ID, error handling, OTel hooks | PARTIALLY COMPLETE | Middleware sets X-Request-ID / X-Correlation-ID; basic logging; TracerProvider | No FastAPI OTel instrumentation; request_id not injected into log records; conversation/message/ai_run_id not in trace context | Complete OTel hooks or mark as stub in docs |

## 24. Day 1 API list

| Area | Status | Notes |
|------|--------|-------|
| AUTH | COMPLETE | login/logout/me |
| CUSTOMERS | COMPLETE | list/create/get/patch |
| CONVERSATIONS | COMPLETE | list/create/get/patch |
| MESSAGES | COMPLETE | list/create under conversation |
| TICKETS | COMPLETE | list/create/get/patch |
| TEAMS | COMPLETE | GET/POST teams; also GET `/users` |
| SYSTEM | COMPLETE | `/api/v1/health` |

## 25. Day 1 acceptance demo

| Step | Status | Notes |
|------|--------|-------|
| Docker up → login → inbox → create customer → web chat → realtime → reply → assign → priority → close → audit | PARTIALLY COMPLETE | End-to-end path exists; audit covers assign/close; smoke test covers customer/conversation/message/close | Manual WS/audit verification not automated |

## Day 1 — Explicit exclusions (should NOT be built)

| Excluded item | Present? | Verdict |
|---------------|----------|---------|
| Production AI agent / RAG / confidence / AI escalation / auto actions | No | Good |
| Stripe / HubSpot / Jira / Slack / WhatsApp / MCP / analytics | No | Good |
| Sentiment product feature (Day 1 ban) | Sentiment field exists on Day 2 `AIClassification` only | Acceptable for Day 2 |

---

# Day 2 — Knowledge Base + AI Foundation

## 1–4. Knowledge domain models

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Module layout (domain/application/infrastructure/api) | COMPLETE | Matches Day 2 tree | — | — |
| KnowledgeSource (URL/PDF/TEXT, status, configuration, last_synced_at) | COMPLETE | Model + migration `0002_knowledge` | — | — |
| Document (+ content_hash, status, metadata) | COMPLETE | Also `error_message` (useful extra) | — | — |
| DocumentChunk with pgvector embedding | COMPLETE | `Vector(1536)` | No ANN index (HNSW/IVFFlat) — OK for MVP volume | Add index when corpus grows |
| content_hash skip-reprocess | COMPLETE | IngestionService skips when hash matches and chunks exist | — | — |

## 5. Ingestion pipeline (TEXT / PDF / URL)

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| TEXT → normalize → chunk → embed → store | COMPLETE | TextLoader + Celery | — | — |
| PDF extract → same pipeline | COMPLETE | pypdf PDFLoader; upload volume shared backend/worker | Blank PDFs extract empty text → FAILED (expected) | Surface clearer UI errors |
| URL fetch → readable content → one URL = one doc | COMPLETE | URLLoader + html_to_text; no crawler | — | — |

## 6. Chunking

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Reusable Chunker interface; token size ~500–800, overlap ~50–100, configurable | COMPLETE | `TokenChunker` defaults 600/80 via settings | Whitespace “tokens” approximate | Optional tiktoken later |

## 7. Embedding provider abstraction

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| EmbeddingProvider with embed_documents / embed_query | COMPLETE | ABC + factory | — | — |
| One real MVP provider (spec example: OpenAI; project chose Gemini LLM but hash embeddings) | INCORRECT | Only `HashEmbeddingProvider` — deterministic, **non-semantic** | Day 2 Flow A requires “relevant” chunks for password FAQ; hash vectors cannot reliably do this across a multi-doc corpus; run-guide admits weak scores | Implement Gemini (or other) embedding provider behind same interface; keep hash for offline tests |

## 8. LangChain integration

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Use LangChain for processing / embeddings / retrievers / structured output / LLM abstraction | MISSING | `langchain` / `langchain-core` in dependencies only; **zero imports in `app/`** | Architecture: KnowledgeService → Retriever interface → **LangChain implementation** not followed; custom SQLAlchemy cosine search instead | Introduce thin LangChain wrappers (e.g. embeddings adapter, PGVector/retriever) behind existing interfaces; keep FastAPI free of LangChain leakage |

## 9–11. Retriever + search API

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Retriever.search / search_with_metadata; top_k=5 configurable | COMPLETE | `PgVectorRetriever` + settings | — | — |
| Metadata on chunks (document_id, source_id, source_type, title, url, language) | COMPLETE | Written during ingest | Filters not implemented (explicitly deferred) | Keep as-is |
| `POST /api/v1/knowledge/search` response shape | COMPLETE | results with document_id, title, content, score | — | — |
| Semantic relevance of search | INCORRECT / PARTIAL | Pipeline works; similarity is hash-based | Demo “relevant chunk” is misleading with multiple documents | Fix embeddings (see §7) |

## 12–18. LangGraph + AIService + AIRun + LLM

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Classification graph: receive → load context → classify → structured output (no retrieval) | PARTIALLY COMPLETE | LangGraph nodes implemented; AIRun saved in `AIService` not as graph node | Spec lists “Save AI Run” as graph step; current split is actually cleaner | Keep save in AIService; optionally add graph node later |
| AIRun model + types CLASSIFICATION/GENERATION/SUMMARY/RETRIEVAL | COMPLETE | Migration `0003_ai_runs` | — | — |
| AIService.classify / generate / summarize; no LangGraph in ConversationService | COMPLETE | Conversation routers do not call AI | No ConversationService class exists | Extract services before combining paths on Day 3 |
| LLMProvider generate / structured_output / stream; one provider | COMPLETE | Gemini + Echo fallback | OpenAI/Anthropic stubs not required | Ensure `GEMINI_API_KEY` for real Flow B |
| AIClassification Pydantic schema + intent taxonomy | COMPLETE | All 9 intents | — | — |
| `POST /api/v1/ai/classify` | COMPLETE | Persists AIRun | — | — |
| Paths independent (no retrieve-in-classify, no auto-reply) | COMPLETE | Separated | — | — |

## 19–20. Knowledge UI + ingestion status

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| Routes `/app/knowledge` and `/app/knowledge/:sourceId` | PARTIALLY COMPLETE | Implemented as `/knowledge` and `/knowledge/:sourceId` | Path prefix differs from spec (`/app/...`) | Rename routes if product wants `/app` prefix; functionally OK |
| Add text / PDF / URL; list; delete; status PENDING→PROCESSING→COMPLETED/FAILED | COMPLETE | KnowledgePage + polling | No in-UI search (API-only; OK for Day 2) | Optional search panel |

## 21. Celery ingestion (202 Accepted)

| Requirement | Status | Current implementation | Missing / incorrect | Recommended fix |
|-------------|--------|------------------------|---------------------|-----------------|
| POST creates pending doc, queues job, returns 202; worker parse/chunk/embed/store | COMPLETE | Document endpoints + `ingest_document` task + shared volume | — | — |

## 22. Day 2 DoD checklist

| Item | Status |
|------|--------|
| Knowledge module / Source / Document / Chunk / pgvector | COMPLETE |
| Text / PDF / URL ingestion | COMPLETE |
| Chunking / Embedding abstraction / Retriever / Search API | PARTIALLY COMPLETE (hash embeddings undermine retrieval) |
| Celery jobs / Ingestion status | COMPLETE |
| LangChain integration | MISSING |
| LangGraph / LLM abstraction / AIService / classification / structured output / AIRun | COMPLETE (with Echo fallback when no Gemini key) |
| Knowledge UI | COMPLETE |
| Tests | PARTIALLY COMPLETE (see below) |

## Day 2 — Explicit exclusions

| Excluded item | Built? | Verdict |
|---------------|--------|---------|
| Full AI support agent / auto-replies / tools / playbooks | No | Good |
| Stripe / HubSpot / Jira / Slack / WhatsApp | No | Good |
| Combining retrieval + generation in one customer flow | No | Good |

---

# Architecture compliance

## Intended Day 1 architecture

```
React ⇄ REST/WS ⇄ FastAPI (auth, org, users, customers, conversations, messages)
                 ⇄ PostgreSQL + Redis
```

**Verdict:** Followed. Support Core is independent of AI chat.

## Intended Day 2 architecture

```
SUPPORT CORE | KNOWLEDGE (ingest/retrieval) | AI SERVICE (LangGraph → LangChain → LLM)
             └──────────── PostgreSQL + pgvector + Redis + Celery ────────────┘
```

**Verdict:** Partially followed.

| Decision | Compliance |
|----------|------------|
| Knowledge and AI paths independent | COMPLETE |
| AIService boundary (not in Conversation/Message services) | COMPLETE |
| Retriever behind interface (not LangChain in every FastAPI handler) | PARTIALLY COMPLETE — interface exists, but implementation is raw SQLAlchemy, not LangChain |
| LangChain as AI infrastructure layer | MISSING |
| LangGraph as orchestration for classification | COMPLETE |
| One LLM provider | COMPLETE (Gemini + echo) |
| One embedding provider suitable for MVP retrieval | INCORRECT (hash-local) |
| Application service layer for conversations | MISSING (router-centric) |
| ChannelAdapter as message entry boundary | PARTIALLY COMPLETE (stubs only) |

## Scope creep / unnecessary work

Nothing from the Day 1/Day 2 **exclusion lists** was built (no Stripe/HubSpot/agent/auto-reply/etc.).

Notable **deviations** (not exclusions, but diverge from docs):

1. Gemini-only LLM (docs originally suggested OpenAI/Anthropic/Gemini points; Day 2 allows one provider) — **acceptable**.
2. Hash embeddings instead of a real embedding provider — **harms Day 2 acceptance quality**.
3. Public unauthenticated conversation APIs — **necessary** for web chat; not excluded.
4. Extra `Document.error_message`, conversation `subject`, soft WS auth — **minor**, not scope creep into banned features.

---

# Testing audit

| Area | Coverage | Gap |
|------|----------|-----|
| Health | `test_health.py` | — |
| API smoke (login, customer, conversation, message, close) | `test_api_smoke.py` (needs running API) | Skips if API down; no WS/audit assertions |
| Knowledge models / routes present | `test_knowledge_models.py` | No RBAC negative tests |
| Chunker + hash embed | `test_chunk_embed.py` | — |
| Loaders + ingest + hash skip | `test_ingestion_loaders.py` | No live URL/Celery e2e |
| Search + classify persistence | `test_search_and_classify.py` | Search test uses single-doc corpus (passes without true semantic ranking) |
| LangGraph minimal + classify | `test_ai_graph.py` | Uses EchoLLM only |
| Gemini wiring | `test_gemini_provider.py` | No live Gemini call (good); no mock of structured_output path |

### Missing tests (recommended before Day 3)

1. Celery `ingest_document` end-to-end (TEXT → COMPLETED → searchable).
2. Semantic retrieval fixture once real embeddings exist (multi-doc ranking).
3. WebSocket fan-out on `message.created`.
4. Audit rows for assign/close.
5. RBAC 403 cases (READ_ONLY cannot write knowledge).
6. ChannelAdapter normalize path (unit).
7. Classification does **not** create customer messages / auto-replies.
8. LangChain adapter unit tests when introduced.

---

# Summary

## 1. Everything that is correct

- Monorepo, Docker Compose (frontend/backend/postgres/redis/worker), Makefile, seed agent, run docs.
- FastAPI health, versioning, OpenAPI, CORS, JWT auth, RBAC permissions, single-tenant Organization.
- Core entities + Alembic (`0001` support core, `0002` knowledge, `0003` ai_runs) with pgvector extension.
- Customer CRUD; conversations/messages (incl. AI sender type); tickets API; teams/users list.
- Web chat + agent inbox (filters, reply, assign, priority, close/reopen) + Redis/WS realtime events.
- Event bus + audit for key conversation/customer/ticket mutations.
- ChannelAdapter stubs (WebChat/Email/Form).
- Day 2 knowledge module: sources/docs/chunks, TEXT/PDF/URL loaders, chunker, Celery 202 ingestion, status UI, search API shape.
- AIService + LangGraph classification + Pydantic intents + AIRun persistence + Gemini/Echo LLM provider.
- Knowledge and AI kept separate; no auto-reply / full agent / banned integrations.
- Meaningful unit/integration tests for models, chunking, ingest, classify (echo), API smoke.

## 2. Everything that needs fixing

| Priority | Issue |
|----------|--------|
| P0 | Replace hash embeddings with a real EmbeddingProvider (Gemini embeddings or equivalent) so Flow A relevance is real |
| P0 | Actually integrate LangChain behind Retriever/Embedding/LLM boundaries (deps exist unused) |
| P1 | Wire ChannelAdapter into conversation/message entry; extract ConversationService |
| P1 | Complete observability: bind request_id to logs; use or trim unused FastAPI OTel instrumentation |
| P2 | Inbox: PENDING status + team assign; fill empty frontend feature folders / `router.tsx` |
| P2 | Audit: `ticket.resolved`; decide on `user.role_changed` |
| P2 | Harden WS auth for agent connections |
| P2 | Align knowledge routes with `/app/knowledge` if product wants exact paths |

## 3. Architectural issues

1. **LangChain missing from the runtime architecture** despite Day 2 DoD and diagrams.
2. **Non-semantic embeddings** break the knowledge foundation Day 3 will combine with generation.
3. **Router-centric domain logic** (no ConversationService/MessageService) will make Day 3 “message → classify → retrieve → draft” harder and risk leaking AI into routers.
4. **Channel adapters not on the hot path** — future WhatsApp/etc. plug-in story is incomplete.
5. **AIRun persistence outside the graph** is fine, but event/`ai.run.*` emission is not yet part of the shared event system.

## 4. Missing tests

- Celery ingestion e2e, multi-doc semantic search, WebSocket events, audit assertions, RBAC negatives, no-auto-reply guarantee, LangChain adapter tests, ChannelAdapter unit tests.

## 5. Ready for Day 3?

**No — not fully ready.**

Day 3 is defined as combining:  
`Customer Message → Intent → Retrieve Knowledge → Generate Grounded Answer → Confidence → draft (human approval)`.

Blockers:

1. Retrieval is not trustworthy for grounding (hash embeddings).
2. LangChain infrastructure layer from the locked architecture is absent.
3. Conversation application service / channel entry boundaries are incomplete for clean AI plug-in.

**Conditional go:** You may start Day 3 scaffolding (draft UI, confidence stub, human-approval gate) **in parallel**, but do not treat Flow A as production-ready grounding until embeddings + LangChain boundaries are fixed.

---

*End of audit.*
