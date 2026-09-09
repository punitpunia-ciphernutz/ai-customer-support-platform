"""Acceptance checks for hybrid_rrf end-to-end validation (no architecture changes)."""

from __future__ import annotations

import pytest

from scripts.validate_hybrid_search import run_validation


@pytest.mark.asyncio
async def test_hybrid_search_e2e_validation_harness() -> None:
    result = await run_validation(repeats=3)
    failed = [c for c in result["checks"] if not c["passed"]]
    assert not failed, f"Failed checks: {failed}"

    metrics = result["metrics"]
    # hybrid_rrf should match or beat legacy on mean Recall@20 for labeled cases
    assert metrics["hybrid_rrf"]["recall_at_20"] >= metrics["legacy"]["recall_at_20"] - 0.01
    # Exact-code strength: RRF mean@5 should be strong on this fixture set
    assert metrics["hybrid_rrf"]["recall_at_5"] >= 0.8
