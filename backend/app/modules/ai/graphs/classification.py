"""LangGraph classification flow — no knowledge retrieval yet."""

from __future__ import annotations

import time
from typing import Any, TypedDict

from app.modules.ai.domain.schemas import AIClassification
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider


class ClassificationState(TypedDict, total=False):
    message: str
    context: dict[str, Any]
    classification: dict[str, Any]
    error: str | None


async def run_classification_graph(
    message: str,
    *,
    context: dict[str, Any] | None = None,
    llm: LLMProvider | None = None,
) -> AIClassification:
    provider = llm or get_llm_provider()

    async def receive(state: ClassificationState) -> ClassificationState:
        return {"message": state["message"], "context": state.get("context") or {}}

    async def load_context(state: ClassificationState) -> ClassificationState:
        # Day 2: light context only — no knowledge retrieval
        ctx = dict(state.get("context") or {})
        ctx.setdefault("message_length", len(state.get("message") or ""))
        return {"context": ctx}

    async def classify(state: ClassificationState) -> ClassificationState:
        result = await provider.structured_output(state["message"], AIClassification)
        return {"classification": result.model_dump(mode="json"), "error": None}

    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(ClassificationState)
        graph.add_node("receive", receive)
        graph.add_node("load_context", load_context)
        graph.add_node("classify", classify)
        graph.add_edge(START, "receive")
        graph.add_edge("receive", "load_context")
        graph.add_edge("load_context", "classify")
        graph.add_edge("classify", END)
        app = graph.compile()
        out = await app.ainvoke({"message": message, "context": context or {}})
        return AIClassification.model_validate(out["classification"])
    except Exception:
        # Fallback without LangGraph
        return await provider.structured_output(message, AIClassification)


async def timed_classification(
    message: str,
    *,
    context: dict[str, Any] | None = None,
    llm: LLMProvider | None = None,
) -> tuple[AIClassification, int]:
    started = time.perf_counter()
    result = await run_classification_graph(message, context=context, llm=llm)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return result, latency_ms
