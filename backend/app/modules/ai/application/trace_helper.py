"""Operational AI run step tracing — no chain-of-thought."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.modules.ai.domain.schemas import AIRunTraceStep


class TraceCollector:
    """Collects trace steps outside LangGraph state merges."""

    def __init__(self) -> None:
        self.steps: list[AIRunTraceStep] = []

    def to_dicts(self) -> list[dict[str, Any]]:
        return [s.model_dump() for s in self.steps]


@asynccontextmanager
async def trace_step(
    collector: TraceCollector,
    name: str,
    *,
    input_summary: str = "",
) -> AsyncIterator[None]:
    started = time.perf_counter()
    step = AIRunTraceStep(name=name, status="running", input_summary=input_summary or None)
    collector.steps.append(step)
    error: str | None = None
    try:
        yield
        step.status = "completed"
    except Exception as exc:  # noqa: BLE001
        step.status = "failed"
        step.error = str(exc)[:500]
        error = step.error
        raise
    finally:
        step.duration_ms = int((time.perf_counter() - started) * 1000)
        if error:
            step.output_summary = f"error: {error}"


def trace_steps_to_dict(steps: list[AIRunTraceStep]) -> list[dict[str, Any]]:
    return [s.model_dump() for s in steps]
