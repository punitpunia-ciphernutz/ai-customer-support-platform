# Day 2 Implementation Plan — Knowledge Base + AI Foundation

**Goal:** Build two independent foundations the eventual AI agent depends on: a reliable **knowledge/retrieval** layer (ingest → chunk → embed → pgvector → search) and a clean **LangGraph AI runtime** (message → classify → structured output → AIRun). Do **not** combine them yet, and do **not** auto-reply to customers.

**Rule:** Knowledge path and AI path ship separately. Day 3 wires them together.

**Depends on:** Day 1 Support Core (auth, org, conversations, messages, Celery, Redis, Postgres + pgvector image).

---

## Acceptance demo (must work end-to-end)

### Flow A — Knowledge

1. Login as Admin/Agent → open **Knowledge Base**
2. Add FAQ as **TEXT**, upload a **PDF**, and add a **URL**
3. Each document shows `PENDING` → `PROCESSING` → `COMPLETED` (or `FAILED`)
4. Celery worker parses, chunks, embeds, stores in pgvector
5. `POST /api/v1/knowledge/search` with `"How do I reset my password?"` returns relevant chunks with scores

### Flow B — AI (classification only)

1. `POST` a message (or call classify API) with `"I cannot log into my account"`
2. `AIService` → LangGraph → LLM → Pydantic-validated structured result
3. `AIRun` row persisted (`CLASSIFICATION`, latency, tokens, input/output)
4. Response includes intent (e.g. `ACCOUNT_ACCESS`), language, confidence — **no** customer-facing auto-reply

No manual DB edits. Knowledge search and classification do not call each other yet.

---

## Recommended order (critical path)

```
1. Knowledge module skeleton + models (Source, Document, Chunk) + Alembic
2. Chunker + EmbeddingProvider abstraction (+ one OpenAI impl)
3. Loaders/parsers: TEXT → PDF → URL
4. IngestionService + Celery jobs (202 Accepted + status)
5. pgvector Retriever + knowledge search API
6. LLMProvider + structured schemas + AIRun model
7. AIService + LangGraph classification graph
8. Knowledge UI (list/add/status/delete)
9. Tests + run both demos
```

```mermaid
flowchart TD
  models[KB_models_and_migration] --> chunk[Chunker]
  models --> emb[EmbeddingProvider]
  chunk --> ingest[IngestionService]
  emb --> ingest
  parsers[TEXT_PDF_URL_loaders] --> ingest
  ingest --> celery[Celery_jobs]
  celery --> store[pgvector_store]
  store --> retriever[Retriever]
  retriever --> searchAPI[Knowledge_search_API]
  searchAPI --> ui[Knowledge_UI]
  llm[LLMProvider] --> aisvc[AIService]
  schemas[Structured_output_schemas] --> aisvc
  airun[AIRun_model] --> aisvc
  aisvc --> graph[LangGraph_classify]
  searchAPI --> demoA[Demo_Flow_A]
  graph --> demoB[Demo_Flow_B]
  ui --> demoA
```

**Parallel after models exist:** LLM/AI path (steps 6–7) can proceed beside ingestion (steps 3–5). UI waits on ingestion status APIs.

---

## Phase A — Knowledge module + domain models

**Depends on:** Day 1 DB/Alembic  
**Unlocks:** ingestion, retrieval, UI

Layout:

```
backend/app/modules/knowledge/
├── domain/
│   ├── models.py
│   └── schemas.py
├── application/
│   ├── knowledge_service.py
│   └── ingestion_service.py
├── infrastructure/
│   ├── loaders/
│   ├── embeddings/
│   ├── vectorstore/
│   └── parsers/
└── api/
    └── routes.py
```

### Entities

| Entity | Purpose |
|--------|---------|
| KnowledgeSource | Org-scoped source (URL / PDF / TEXT) |
| Document | Ingested unit with `content_hash` for skip-reprocess |
| DocumentChunk | Chunk text + pgvector `embedding` + metadata |

### KnowledgeSource fields

`id`, `organization_id`, `name`, `type`, `status`, `configuration`, `last_synced_at`, `created_at`, `updated_at`

**Types (Day 2 only):** `URL`, `PDF`, `TEXT`  
**Defer:** Notion, Google Drive, Help Center, API

### Document fields

`id`, `knowledge_source_id`, `title`, `source_url`, `content`, `content_hash`, `metadata`, `status`, `created_at`, `updated_at`

**Hash rule:** fetch → hash → same hash ⇒ skip re-embed; different ⇒ reprocess.

### DocumentChunk fields

`id`, `document_id`, `content`, `chunk_index`, `token_count`, `metadata`, `embedding` (pgvector), `created_at`

### Status enums (source/document)

`PENDING` | `PROCESSING` | `COMPLETED` | `FAILED`

### Tasks

- [x] Create module package + wire router under `/api/v1/knowledge`
- [x] SQLAlchemy models + Alembic migration (pgvector column on chunks)
- [x] Pydantic request/response schemas
- [x] Org-scoped queries; RBAC permission(s) e.g. `knowledge.read` / `knowledge.write`
- [x] Do **not** introduce a separate vector DB

---

## Phase B — Chunking + embedding abstraction

**Depends on:** A  
**Unlocks:** ingestion pipeline

### Chunker

- [x] Reusable `Chunker` interface: `chunk(text) → list[Chunk]` + metadata
- [x] Token-based chunking with overlap (configurable, not hard-coded constants)
- [x] Defaults: ~500–800 tokens, overlap ~50–100 tokens

### EmbeddingProvider

```
EmbeddingProvider
├── embed_documents(texts) → vectors
└── embed_query(text) → vector
```

- [x] Abstract interface in knowledge infrastructure
- [x] One MVP implementation (e.g. OpenAI embeddings via LangChain)
- [x] Config: model name, dimensions, API key from settings
- [x] Do not call OpenAI directly from FastAPI route handlers

---

## Phase C — Ingestion pipeline (TEXT / PDF / URL)

**Depends on:** B  
**Unlocks:** Celery jobs, search quality

### Pipelines

| Type | Steps |
|------|--------|
| TEXT | Normalize → Chunk → Embed → Store |
| PDF | Extract text → Normalize → Chunk → Embed → Store |
| URL | Fetch → Extract readable content → Normalize → Chunk → Embed → Store |

### Tasks

- [x] TEXT loader (raw body / pasted content)
- [x] PDF parser (text extract only; no OCR requirement for Day 2)
- [x] URL loader: **one URL → one document** (no crawler / sitemap)
- [x] Normalize whitespace/encoding before chunking
- [x] Persist document + chunks; set `content_hash`
- [x] Attach chunk metadata for future filters, e.g.:

```json
{
  "document_id": "...",
  "source_id": "...",
  "source_type": "PDF",
  "title": "...",
  "url": "...",
  "language": "en"
}
```

- [x] Design metadata so language/product/version filters can be added later — do not build full filter UI yet

### LangChain boundary

- [x] Use LangChain for document processing / embeddings where useful
- [x] Keep LangChain behind KnowledgeService / infrastructure — **no** LangChain types leaking into every FastAPI service

---

## Phase D — Celery ingestion jobs + APIs

**Depends on:** C  
**Unlocks:** async status UI, searchable corpus

**Bad:** parse/embed inside the HTTP request.  
**Good:** create source/document → queue job → `202` → Celery does the work.

### Tasks

- [x] `POST` create source / add document returns quickly (`202` where appropriate)
- [x] Celery task: parse → chunk → embed → store; update status on success/failure
- [x] Persist error message on `FAILED`
- [x] APIs: list sources, list documents, get status, delete document (and chunks)
- [x] Idempotent-ish re-ingest via `content_hash` when re-syncing URL/text

### Suggested endpoints (adjust names to match existing style)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/api/v1/knowledge/sources` | Create source |
| GET | `/api/v1/knowledge/sources` | List |
| GET | `/api/v1/knowledge/sources/{id}` | Detail + documents |
| POST | `/api/v1/knowledge/sources/{id}/documents` | Text / PDF upload / URL |
| DELETE | `/api/v1/knowledge/documents/{id}` | Cascade chunks |
| POST | `/api/v1/knowledge/search` | Retrieval (Phase E) |

---

## Phase E — Retriever + knowledge search API

**Depends on:** D (at least some completed docs)  
**Unlocks:** Flow A demo

### Retriever interface

```
Retriever
├── search(query) → chunks
└── search_with_metadata(query) → chunks + metadata/scores
```

### Behavior

```
Query → embed_query → pgvector similarity → top_k chunks
```

- [x] `top_k` configurable (default `5`)
- [x] Org (and optionally source) scoping in SQL
- [x] `POST /api/v1/knowledge/search`

**Request:**

```json
{ "query": "How do I reset my password?" }
```

**Response shape:**

```json
{
  "results": [
    {
      "document_id": "...",
      "title": "Password Reset",
      "content": "...",
      "score": 0.91
    }
  ]
}
```

- [x] LangChain retriever implementation behind the interface (optional wrapper), not called from random services

---

## Phase F — LLM provider + structured output + AIRun

**Depends on:** Day 1 AI placeholders (extend, don’t fork)  
**Unlocks:** classification graph

### LLMProvider

```
LLMProvider
├── generate()
├── structured_output()
└── stream()
```

- [x] Interface + **one** provider impl (OpenAI or whatever Day 1 Echo was preparing for)
- [x] Do not wire Anthropic + Gemini on Day 2

### Structured schemas

```
AIClassification
├── intent
├── language
├── sentiment
├── confidence
└── requires_human
```

- [x] Pydantic models; LLM output → validate → typed object
- [x] Intent taxonomy (configurable later; hard-list OK for Day 2):

`GENERAL_QUESTION` · `ACCOUNT_ACCESS` · `BILLING` · `TECHNICAL_ISSUE` · `BUG_REPORT` · `FEATURE_REQUEST` · `REFUND` · `CANCELLATION` · `OTHER`

### AIRun model

`id`, `conversation_id`, `message_id`, `type`, `status`, `model`, `input`, `output`, `latency_ms`, `token_usage`, `error`, `created_at`

**Types (Day 2):** `CLASSIFICATION`, `GENERATION`, `SUMMARY`, `RETRIEVAL`  
**Defer:** `AGENT`, `TOOL_CALL`, `ESCALATION`

- [x] Alembic migration for `AIRun`
- [x] Persist every classification run (success and failure when possible)

---

## Phase G — AIService + LangGraph classification

**Depends on:** F  
**Unlocks:** Flow B demo

### Boundary

```
ConversationService / API
       ↓
   AIService
       ↓
   LangGraph
       ↓
   LangChain / LLMProvider
```

- [x] `AIService.classify()` (and stubs or thin wrappers for `generate()` / `summarize()` if useful — **not** customer-facing yet)
- [x] **No** LangGraph inside ConversationService / MessageService / TicketService

### Day 2 graph (classification only)

```
START → Receive Message → Load Context → Classify Intent
      → Structured Output → Save AIRun → END
```

- [x] Input example: `{ "message": "I cannot log into my account" }`
- [x] Output: intent, language, `requires_human`, confidence (and sentiment if schema includes it)
- [x] Load minimal context only (e.g. message text ± light conversation metadata) — **no** knowledge retrieval node yet
- [x] Expose via internal/API route suitable for demo (dedicated classify endpoint or message hook that records AIRun without sending an AI reply)

---

## Phase H — Knowledge UI

**Depends on:** D (status APIs); search optional for UI  
**Unlocks:** Flow A from the browser

Routes:

- `/app/knowledge`
- `/app/knowledge/:sourceId`

### Day 2 functionality

- [x] List knowledge sources
- [x] Add knowledge: text, PDF upload, URL
- [x] List documents under a source
- [x] Show ingestion status: `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED`
- [x] Delete document
- [x] Poll or refresh status while processing

Skeleton layout: Knowledge Base header → Add Knowledge → Sources list → Documents list. Match existing Day 1 UI patterns (inbox/customers); no new design system.

---

## Phase I — Tests + docs touch-up

**Depends on:** E + G (+ H for smoke)  
**Unlocks:** Definition of Done

### Backend

- [x] Unit: chunker sizes/overlap; content_hash skip logic
- [x] Unit: EmbeddingProvider / LLMProvider with mocks
- [x] Unit: LangGraph classification → valid `AIClassification`
- [x] Integration: Celery task (or sync test double) TEXT ingest → chunks stored
- [x] API: knowledge search returns ranked results against seeded FAQ
- [x] API: classify persists `AIRun` with `CLASSIFICATION` type

### Frontend

- [x] Smoke: knowledge page renders; create text source/document happy path (if E2E harness exists; otherwise manual checklist)

### Docs

- [x] Note Day 2 env vars (embedding/LLM keys, chunk settings) in `.env.example` / run guide — no secrets committed
- [x] Update `docs/progress.md` when phases complete

---

## Definition of Done checklist

- [x] Knowledge module
- [x] KnowledgeSource / Document / DocumentChunk
- [x] pgvector embeddings on chunks
- [x] Text / PDF / URL ingestion
- [x] Chunking (configurable token + overlap)
- [x] Embedding abstraction (+ one provider)
- [x] Retriever + `POST /api/v1/knowledge/search`
- [x] Celery ingestion jobs + status lifecycle
- [x] LangChain behind knowledge/AI boundaries
- [x] LLM provider abstraction (+ one provider)
- [x] AIService
- [x] LangGraph classification flow
- [x] Structured AI output (Pydantic)
- [x] AI Run persistence
- [x] Basic Knowledge UI
- [x] Tests covering ingest/search and classify/AIRun
- [x] Flow A + Flow B demos pass

---

## Out of scope (Do NOT build on Day 2)

- Full AI support agent / auto-replies to customers
- Combining retrieval + generation in one graph
- Autonomous actions, tool calling, playbooks, automation builder
- Stripe, HubSpot, Jira, Slack, WhatsApp
- Multi-URL crawlers / Notion / Drive / Help Center connectors
- Production confidence algorithm / advanced analytics
- Multiple LLM or embedding providers beyond one MVP each

---

## Target architecture (end of Day 2)

```
                    FASTAPI
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   SUPPORT CORE    KNOWLEDGE       AI SERVICE
        │              │              │
  Conversations     Ingestion      LangGraph
  Messages          Retrieval         │
  Customers             │         LangChain
  Tickets               │             │
        │               │         LLMProvider
        └───────┬───────┴─────────────┘
                │
           PostgreSQL + pgvector
                │
              Redis → Celery → ingestion jobs
```

**Next (Day 3 preview):** Customer message → Intent → Retrieve knowledge → Grounded answer → Confidence → draft/response with human approval still required before autonomy.
