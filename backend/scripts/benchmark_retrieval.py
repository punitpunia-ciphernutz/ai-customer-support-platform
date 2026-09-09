#!/usr/bin/env python3
"""Lightweight retrieval latency harness (legacy vs hybrid_rrf).

Usage (inside backend container or venv with DB access):

  python -m scripts.benchmark_retrieval
  python -m scripts.benchmark_retrieval --mode both --queries 5 --repeats 3

Does not flip production defaults. Uses OfflineSemanticEmbeddingProvider.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

from sqlalchemy import select

from app.infrastructure.database.models import Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever

DEFAULT_QUERIES = [
    "How do I reset my password?",
    "What does AUTH-401 mean?",
    "update billing address invoice",
    "unrelated office plants watering",
]


async def _time_search(hybrid: HybridRetriever, query: str, org_id: str, mode: str, repeats: int) -> list[float]:
    state = SupportAgentState(user_message=query)
    samples: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        await hybrid.search(state, organization_id=org_id, mode=mode)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return samples


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark hybrid retrieval modes")
    parser.add_argument("--mode", choices=["legacy", "hybrid_rrf", "both"], default="both")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--queries", type=int, default=len(DEFAULT_QUERIES))
    args = parser.parse_args()

    queries = DEFAULT_QUERIES[: max(1, args.queries)]
    modes = ["legacy", "hybrid_rrf"] if args.mode == "both" else [args.mode]

    provider = OfflineSemanticEmbeddingProvider(dimensions=1536)
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        retriever = PgVectorRetriever(session, embedding_provider=provider)

        print(f"org={org_id} repeats={args.repeats} queries={len(queries)}")
        for mode in modes:
            hybrid = HybridRetriever(session, retriever=retriever, mode=mode)
            all_ms: list[float] = []
            for q in queries:
                samples = await _time_search(hybrid, q, org_id, mode, args.repeats)
                all_ms.extend(samples)
                p50 = statistics.median(samples)
                print(f"  [{mode}] {q[:48]!r:50} p50={p50:.1f}ms samples={samples}")
            if all_ms:
                all_ms_sorted = sorted(all_ms)
                p95_idx = min(len(all_ms_sorted) - 1, int(0.95 * (len(all_ms_sorted) - 1)))
                print(
                    f"  [{mode}] overall p50={statistics.median(all_ms):.1f}ms "
                    f"p95={all_ms_sorted[p95_idx]:.1f}ms n={len(all_ms)}"
                )


if __name__ == "__main__":
    asyncio.run(main())
