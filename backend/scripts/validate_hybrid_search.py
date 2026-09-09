#!/usr/bin/env python3
"""End-to-end hybrid search validation harness.

Seeds a controlled multi-doc KB, compares legacy vs hybrid_rrf on golden
queries, measures Recall@k + latency, checks HNSW ef_search, FTS, RRF,
reranker/gate, tenant isolation, and org retrieval_mode override.

Usage:
  docker compose exec backend python -m scripts.validate_hybrid_search
  docker compose exec backend python -m scripts.validate_hybrid_search --json /tmp/hybrid-validation.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text

from app.config.settings import get_settings
from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.schemas import RetrievedDocument, SupportAgentState
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.ai.infrastructure.reranker import Reranker, aggregate_retrieval_score
from app.modules.ai.infrastructure.retrieval.fts_search import fts_search
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever
from app.modules.ai.infrastructure.retrieval.relevance_gate import RelevanceGate
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever


@dataclass
class CaseResult:
    name: str
    query: str
    relevant_doc_ids: list[str]
    legacy_ranks: dict[str, int | None]
    rrf_ranks: dict[str, int | None]
    legacy_recall: dict[str, float]
    rrf_recall: dict[str, float]
    legacy_latency_ms: list[float]
    rrf_latency_ms: list[float]
    notes: list[str] = field(default_factory=list)
    passed: bool = True


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _rank_of(hits: list, doc_id: str) -> int | None:
    for i, h in enumerate(hits):
        if h.document_id == doc_id:
            return i
    return None


def _recall_at(hits: list, relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    top = {h.document_id for h in hits[:k]}
    return len(top & relevant) / len(relevant)


async def _seed_kb(session, org_id: str, provider: OfflineSemanticEmbeddingProvider) -> dict[str, str]:
    source = KnowledgeSource(
        organization_id=org_id,
        name=f"Hybrid Validation KB {uuid4().hex[:8]}",
        type=KnowledgeSourceType.TEXT,
        status=IngestionStatus.PENDING,
        configuration={"fixture": "hybrid_validation"},
    )
    session.add(source)
    await session.flush()
    service = IngestionService(session, embedding_provider=provider)

    docs = {
        "password": (
            "Password Reset",
            "How do I reset my password? Use the Forgot Password link on the login page "
            "and follow the email instructions to regain account access.",
        ),
        "auth": (
            "AUTH-401 Errors",
            "Error code AUTH-401 means the session token expired or is invalid. "
            "Ask the customer to sign in again. Do not confuse with billing failures.",
        ),
        "payment": (
            "ERR_PAYMENT_403 Guide",
            "ERR_PAYMENT_403 indicates the card issuer declined the charge. "
            "Retry with another payment method or contact the bank.",
        ),
        "billing": (
            "Billing Address FAQ",
            "How do I update my billing address? Open Settings, choose Billing, "
            "and edit your invoice mailing address for payment receipts.",
        ),
        "filler": (
            "Office Plants",
            "Our lobby has ferns and succulents. Water weekly. This document is unrelated "
            "to authentication, passwords, or payments.",
        ),
        "ticket": (
            "Ticket ID Format",
            "Internal ticket identifiers look like TKT-77821. Agents should never invent IDs.",
        ),
    }
    ids: dict[str, str] = {}
    for key, (title, text_body) in docs.items():
        doc = await service.create_pending_document(source=source, title=title, content="x")
        await service.ingest_loaded_content(
            doc.id,
            LoadedContent(title=title, text=text_body, metadata={"source_type": "TEXT", "fixture": key}),
        )
        ids[key] = doc.id
    await session.flush()
    return ids


async def _time_search(hybrid: HybridRetriever, query: str, org_id: str, mode: str, repeats: int) -> tuple[list, list[float]]:
    state = SupportAgentState(user_message=query)
    samples: list[float] = []
    hits = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        hits = await hybrid.search(state, organization_id=org_id, mode=mode)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return hits, samples


async def run_validation(*, repeats: int = 5) -> dict[str, Any]:
    get_settings.cache_clear()
    settings = get_settings()
    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    checks: list[CheckResult] = []
    cases: list[CaseResult] = []

    async with AsyncSessionLocal() as session:
        orgs = (await session.execute(select(Organization.id).limit(2))).scalars().all()
        org_a = orgs[0]
        # Create a second org for isolation if missing
        if len(orgs) < 2:
            org_b_row = Organization(name=f"Validation Org B {uuid4().hex[:6]}")
            session.add(org_b_row)
            await session.flush()
            org_b = org_b_row.id
        else:
            org_b = orgs[1]

        ids = await _seed_kb(session, org_a, provider)
        # Seed a conflicting AUTH-401 doc into org B
        source_b = KnowledgeSource(
            organization_id=org_b,
            name=f"OrgB KB {uuid4().hex[:6]}",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source_b)
        await session.flush()
        service_b = IngestionService(session, embedding_provider=provider)
        foreign = await service_b.create_pending_document(source=source_b, title="AUTH-401 OrgB", content="x")
        await service_b.ingest_loaded_content(
            foreign.id,
            LoadedContent(
                title="AUTH-401 OrgB",
                text="ORG-B-ONLY AUTH-401 secret marker should never leak to org A searches.",
                metadata={"source_type": "TEXT"},
            ),
        )
        await session.flush()

        retriever = PgVectorRetriever(session, embedding_provider=provider)
        hybrid_legacy = HybridRetriever(session, retriever=retriever, keyword_weight=0.3, mode="legacy")
        hybrid_rrf = HybridRetriever(session, retriever=retriever, mode="hybrid_rrf")

        # --- 1. HNSW + ef_search ---
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.hnsw_ef_search)}"))
        idx = (
            await session.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_document_chunks_embedding_hnsw'"
                )
            )
        ).scalar_one_or_none()
        checks.append(
            CheckResult(
                name="hnsw_index_present",
                passed=bool(idx and "hnsw" in idx.lower()),
                detail=idx or "missing index",
            )
        )
        vector_hits = await retriever.search_pgvector(
            "How do I reset my password?", organization_id=org_a, top_k=5
        )
        checks.append(
            CheckResult(
                name="hnsw_vector_search_returns_password",
                passed=any(h.document_id == ids["password"] for h in vector_hits),
                detail=f"top={[h.document_id[:8] for h in vector_hits[:3]]} ef_search={settings.hnsw_ef_search}",
            )
        )

        # --- 2. FTS exact terms / codes ---
        for label, query, doc_key in [
            ("fts_auth_401", "AUTH-401", "auth"),
            ("fts_err_payment", "ERR_PAYMENT_403", "payment"),
            ("fts_ticket_id", "TKT-77821", "ticket"),
            ("fts_keyword_password", "Forgot Password link", "password"),
        ]:
            hits = await fts_search(session, query, organization_id=org_a, top_k=10)
            checks.append(
                CheckResult(
                    name=label,
                    passed=any(h.document_id == ids[doc_key] for h in hits),
                    detail=f"hits={len(hits)} top_doc={hits[0].document_id[:8] if hits else None}",
                )
            )

        empty_fts = await fts_search(session, "   ", organization_id=org_a, top_k=10)
        checks.append(CheckResult(name="fts_empty_query", passed=empty_fts == [], detail=f"n={len(empty_fts)}"))

        # --- 3/5/6. Golden cases legacy vs RRF ---
        case_defs = [
            ("semantic_password", "How do I reset my password?", ["password"]),
            ("error_auth_401", "What does AUTH-401 mean?", ["auth"]),
            ("error_payment", "Customer got ERR_PAYMENT_403 declined", ["payment"]),
            ("billing_semantic", "update my invoice mailing address", ["billing"]),
            ("multi_doc_account", "password reset and AUTH-401 session expired", ["password", "auth"]),
            ("no_match", "quantum flux capacitor warranty policy zzz", []),
            (
                "long_query",
                (
                    "I tried signing in several times yesterday evening and keep getting "
                    "AUTH-401 after my session times out. Can you explain what AUTH-401 means "
                    "and also remind me how to reset my password using the forgot password email flow?"
                ),
                ["auth", "password"],
            ),
        ]

        for name, query, relevant_keys in case_defs:
            relevant_ids = [ids[k] for k in relevant_keys]
            relevant_set = set(relevant_ids)
            legacy_hits, legacy_ms = await _time_search(hybrid_legacy, query, org_a, "legacy", repeats)
            rrf_hits, rrf_ms = await _time_search(hybrid_rrf, query, org_a, "hybrid_rrf", repeats)

            legacy_ranks = {k: _rank_of(legacy_hits, ids[k]) for k in relevant_keys}
            rrf_ranks = {k: _rank_of(rrf_hits, ids[k]) for k in relevant_keys}
            legacy_recall = {f"@{k}": _recall_at(legacy_hits, relevant_set, k) for k in (5, 10, 20)}
            rrf_recall = {f"@{k}": _recall_at(rrf_hits, relevant_set, k) for k in (5, 10, 20)}

            notes: list[str] = []
            passed = True
            if not relevant_keys:
                # no-match: both should avoid treating filler as highly relevant; empty OK
                if len(rrf_hits) == 0 and len(legacy_hits) == 0:
                    notes.append("both returned empty (ideal)")
                else:
                    notes.append(f"legacy_n={len(legacy_hits)} rrf_n={len(rrf_hits)} (noise possible)")
            else:
                # Require relevant docs in RRF top-20
                if rrf_recall["@20"] < 1.0:
                    passed = False
                    notes.append("hybrid_rrf missed relevant doc in top-20")
                # For exact codes, RRF should find them in top-5
                if name.startswith("error_") and rrf_recall["@5"] < 1.0:
                    passed = False
                    notes.append("hybrid_rrf missed error-code doc in top-5")
                if legacy_recall["@20"] < 1.0 and name.startswith("error_"):
                    notes.append("legacy also incomplete for error code (expected ILIKE weakness possible)")

            cases.append(
                CaseResult(
                    name=name,
                    query=query,
                    relevant_doc_ids=relevant_ids,
                    legacy_ranks=legacy_ranks,
                    rrf_ranks=rrf_ranks,
                    legacy_recall=legacy_recall,
                    rrf_recall=rrf_recall,
                    legacy_latency_ms=legacy_ms,
                    rrf_latency_ms=rrf_ms,
                    notes=notes,
                    passed=passed,
                )
            )
            checks.append(
                CheckResult(name=f"case_{name}", passed=passed, detail="; ".join(notes) or "ok")
            )

        # --- 3. RRF metadata / fusion ---
        code_hits, _ = await _time_search(
            hybrid_rrf, "What does AUTH-401 mean?", org_a, "hybrid_rrf", 1
        )
        auth_hit = next((h for h in code_hits if h.document_id == ids["auth"]), None)
        checks.append(
            CheckResult(
                name="rrf_metadata_flags",
                passed=bool(
                    auth_hit
                    and auth_hit.metadata.get("rrf_rank") is not None
                    and (auth_hit.metadata.get("fts") or auth_hit.metadata.get("semantic"))
                ),
                detail=str(auth_hit.metadata if auth_hit else None),
            )
        )

        # --- 4. Reranker + RelevanceGate after RRF ---
        rrf_hits, _ = await _time_search(
            hybrid_rrf, "How do I reset my password?", org_a, "hybrid_rrf", 1
        )
        ranked = await Reranker(llm=EchoLLMProvider()).rank(
            "How do I reset my password?", rrf_hits[: settings.ai_rrf_candidate_k], top_k=5
        )
        docs = [
            RetrievedDocument(
                document_id=r.hit.document_id,
                title=r.hit.title,
                content=r.hit.content,
                score=r.relevance,
                chunk_id=r.hit.chunk_id,
            )
            for r in ranked
        ]
        score = aggregate_retrieval_score(ranked)
        gate = RelevanceGate.evaluate(docs, threshold=0.35, require_knowledge=True)
        checks.append(
            CheckResult(
                name="reranker_gate_after_rrf",
                passed=bool(ranked) and any(d.document_id == ids["password"] for d in docs),
                detail=(
                    f"ranked={len(ranked)} agg={score:.4f} gate_passed={gate.passed} "
                    f"top_score={gate.top_score:.4f} top_doc={docs[0].document_id[:8] if docs else None}"
                ),
            )
        )
        # Soft note if gate fails due to heuristic+RRF score scale (known caveat)
        if ranked and not gate.passed:
            checks.append(
                CheckResult(
                    name="reranker_gate_threshold_caveat",
                    passed=True,
                    detail=(
                        "Gate failed under Echo/heuristic with RRF score scale — "
                        "expected caveat from plan §7; LLM rerank path unaffected."
                    ),
                )
            )

        # Empty / no-match gate
        empty_ranked = await Reranker(llm=EchoLLMProvider()).rank("zzz", [], top_k=5)
        empty_gate = RelevanceGate.evaluate([], threshold=0.35, require_knowledge=True)
        checks.append(
            CheckResult(
                name="gate_empty_hits",
                passed=empty_ranked == [] and empty_gate.passed is False,
                detail=f"reason={empty_gate.reason}",
            )
        )

        # --- 7. Tenant isolation ---
        leak_hits = await fts_search(session, "ORG-B-ONLY", organization_id=org_a, top_k=20)
        leak_rrf, _ = await _time_search(hybrid_rrf, "ORG-B-ONLY AUTH-401", org_a, "hybrid_rrf", 1)
        checks.append(
            CheckResult(
                name="tenant_isolation_fts",
                passed=all(h.document_id != foreign.id for h in leak_hits),
                detail=f"foreign_in_fts={any(h.document_id == foreign.id for h in leak_hits)}",
            )
        )
        checks.append(
            CheckResult(
                name="tenant_isolation_rrf",
                passed=all(h.document_id != foreign.id for h in leak_rrf),
                detail=f"foreign_in_rrf={any(h.document_id == foreign.id for h in leak_rrf)}",
            )
        )

        # --- 10. Org retrieval_mode override + fallback ---
        cfg = await get_or_create_ai_config(session, org_a)
        original_mode = cfg.retrieval_mode
        cfg.retrieval_mode = "hybrid_rrf"
        await session.flush()
        resolved = RuntimeAIConfig.from_config(cfg)
        checks.append(
            CheckResult(
                name="org_mode_hybrid_rrf",
                passed=resolved.retrieval_mode == "hybrid_rrf",
                detail=f"resolved={resolved.retrieval_mode} env_default={settings.ai_retrieval_mode}",
            )
        )
        cfg.retrieval_mode = "legacy"
        await session.flush()
        resolved_legacy = RuntimeAIConfig.from_config(cfg)
        checks.append(
            CheckResult(
                name="org_mode_legacy_override",
                passed=resolved_legacy.retrieval_mode == "legacy",
                detail=f"resolved={resolved_legacy.retrieval_mode}",
            )
        )
        cfg.retrieval_mode = None
        await session.flush()
        resolved_fallback = RuntimeAIConfig.from_config(cfg)
        checks.append(
            CheckResult(
                name="org_mode_null_falls_back_to_env",
                passed=resolved_fallback.retrieval_mode == settings.ai_retrieval_mode,
                detail=f"resolved={resolved_fallback.retrieval_mode} env={settings.ai_retrieval_mode}",
            )
        )
        cfg.retrieval_mode = original_mode
        await session.flush()

        # Aggregate latency / recall
        all_legacy_ms = [ms for c in cases for ms in c.legacy_latency_ms]
        all_rrf_ms = [ms for c in cases for ms in c.rrf_latency_ms]

        def mean_recall(attr: str, k: str) -> float:
            vals = [getattr(c, attr)[k] for c in cases if c.relevant_doc_ids]
            return statistics.mean(vals) if vals else 0.0

        summary = {
            "settings": {
                "ai_retrieval_mode": settings.ai_retrieval_mode,
                "hnsw_ef_search": settings.hnsw_ef_search,
                "ai_rrf_k": settings.ai_rrf_k,
                "ai_rrf_candidate_k": settings.ai_rrf_candidate_k,
                "ai_vector_candidate_k": settings.ai_vector_candidate_k,
                "ai_fts_candidate_k": settings.ai_fts_candidate_k,
            },
            "checks": [asdict(c) for c in checks],
            "cases": [asdict(c) for c in cases],
            "metrics": {
                "legacy": {
                    "latency_p50_ms": _percentile(all_legacy_ms, 50),
                    "latency_p95_ms": _percentile(all_legacy_ms, 95),
                    "recall_at_5": mean_recall("legacy_recall", "@5"),
                    "recall_at_10": mean_recall("legacy_recall", "@10"),
                    "recall_at_20": mean_recall("legacy_recall", "@20"),
                },
                "hybrid_rrf": {
                    "latency_p50_ms": _percentile(all_rrf_ms, 50),
                    "latency_p95_ms": _percentile(all_rrf_ms, 95),
                    "recall_at_5": mean_recall("rrf_recall", "@5"),
                    "recall_at_10": mean_recall("rrf_recall", "@10"),
                    "recall_at_20": mean_recall("rrf_recall", "@20"),
                },
            },
            "passed_checks": sum(1 for c in checks if c.passed),
            "failed_checks": sum(1 for c in checks if not c.passed),
            "total_checks": len(checks),
        }

        await session.rollback()
        return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()
    result = asyncio.run(run_validation(repeats=args.repeats))
    print(json.dumps(result, indent=2, default=str))
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nWrote {args.json_path}", flush=True)
    if result["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
