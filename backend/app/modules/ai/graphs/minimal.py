"""Minimal LangGraph: START → Input → Model → Output → END.

Validates AI infrastructure without coupling to support chat.
"""

from typing import Any, TypedDict


class GraphState(TypedDict):
    input: str
    output: str


def _echo_model(state: GraphState) -> GraphState:
    return {"input": state["input"], "output": f"[minimal-graph] {state['input']}"}


async def run_minimal_graph(text: str) -> dict[str, Any]:
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(GraphState)
        graph.add_node("model", _echo_model)
        graph.add_edge(START, "model")
        graph.add_edge("model", END)
        app = graph.compile()
        return await app.ainvoke({"input": text, "output": ""})
    except Exception:
        # Fallback if langgraph is unavailable in a given environment
        return _echo_model({"input": text, "output": ""})
