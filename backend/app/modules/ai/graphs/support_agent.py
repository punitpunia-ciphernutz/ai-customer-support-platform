"""LangGraph support agent — context, intent, retrieval, generation, confidence, decision."""

from __future__ import annotations

import time
from typing import Any

from app.config import get_settings
from app.modules.ai.application.confidence import calculate_support_confidence
from app.modules.ai.application.escalation import detect_human_request, evaluate_escalation
from app.modules.ai.domain.models import AIConfig
from app.modules.ai.domain.schemas import (
    AIClassification,
    AgentDecision,
    Citation,
    GeneratedAnswer,
    IntentLabel,
    RetrievedDocument,
    SupportAgentState,
)
from app.modules.ai.graphs.classification import run_classification_graph
from app.modules.ai.infrastructure.llm.providers import LLMProvider, get_llm_provider
from app.modules.ai.infrastructure.reranker import Reranker, aggregate_retrieval_score
from app.modules.ai.prompts import PROMPT_VERSION, render_escalation_summary_prompt, render_generate_prompt
from app.modules.knowledge.infrastructure.vectorstore.retriever import PgVectorRetriever, Retriever


async def run_support_agent_graph(
    state: SupportAgentState,
    *,
    config: AIConfig,
    llm: LLMProvider | None = None,
    retriever: Retriever | None = None,
    db_session: Any = None,
) -> SupportAgentState:
    provider = llm or get_llm_provider()
    settings = get_settings()

    async def load_context_node(s: SupportAgentState) -> dict[str, Any]:
        return {}

    async def classify_intent_node(s: SupportAgentState) -> dict[str, Any]:
        human_requested = detect_human_request(s.user_message)
        classification = await run_classification_graph(
            s.user_message,
            context={"history": [t.model_dump() for t in s.conversation_history]},
            llm=provider,
        )
        return {
            "intent": classification.intent,
            "intent_confidence": classification.confidence,
            "sentiment": classification.sentiment,
            "human_requested": human_requested or classification.requires_human,
        }

    async def retrieve_knowledge_node(s: SupportAgentState) -> dict[str, Any]:
        if db_session is None or not s.organization_id:
            return {"retrieved_documents": [], "retrieval_score": 0.0}
        store = retriever or PgVectorRetriever(db_session)
        query = s.user_message
        if s.intent == IntentLabel.ACCOUNT_ACCESS and "password" not in query.lower():
            query = f"{query} password account access"
        hits = await store.search(
            query,
            organization_id=s.organization_id,
            top_k=settings.ai_retrieval_top_k,
        )
        ranked = await Reranker(llm=provider).rank(
            s.user_message, hits, top_k=settings.ai_final_top_k
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
        return {"retrieved_documents": docs, "retrieval_score": score}

    async def evaluate_retrieved_context_node(s: SupportAgentState) -> dict[str, Any]:
        if s.retrieval_score < settings.ai_min_retrieval_score:
            return {"escalation_required": True, "escalation_reason": "No sufficiently relevant knowledge found"}
        return {}

    async def generate_answer_node(s: SupportAgentState) -> dict[str, Any]:
        prompt = render_generate_prompt(s)
        answer = await _generate_answer(provider, prompt, s)
        citations = [
            Citation(document_id=d.document_id, title=d.title, chunk_id=d.chunk_id)
            for d in s.retrieved_documents[:3]
            if d.score >= settings.ai_min_retrieval_score
        ]
        grounded = answer.grounded and bool(citations)
        draft = answer.answer
        if answer.needs_clarification and not grounded:
            draft = answer.answer
        return {
            "draft_response": draft,
            "grounded": grounded,
            "citations": citations,
        }

    async def calculate_confidence_node(s: SupportAgentState) -> dict[str, Any]:
        confidence = calculate_support_confidence(s)
        return {"support_confidence": confidence}

    async def decision_node(s: SupportAgentState) -> dict[str, Any]:
        updated = evaluate_escalation(s, config)
        if updated.decision == AgentDecision.AI_RESOLVE:
            return {
                "escalation_required": False,
                "decision": AgentDecision.AI_RESOLVE,
                "final_response": s.draft_response,
            }
        summary_prompt = render_escalation_summary_prompt(updated)
        summary = await provider.generate(summary_prompt)
        return {
            "escalation_required": True,
            "escalation_reason": updated.escalation_reason,
            "decision": AgentDecision.ESCALATE,
            "escalation_summary": summary[:2000],
            "final_response": None,
        }

    async def finalize_response_node(s: SupportAgentState) -> dict[str, Any]:
        return {"final_response": s.draft_response}

    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(SupportAgentState)
        graph.add_node("load_context", load_context_node)
        graph.add_node("classify_intent", classify_intent_node)
        graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
        graph.add_node("evaluate_retrieved_context", evaluate_retrieved_context_node)
        graph.add_node("generate_answer", generate_answer_node)
        graph.add_node("calculate_confidence", calculate_confidence_node)
        graph.add_node("decision", decision_node)
        graph.add_node("finalize_response", finalize_response_node)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "classify_intent")
        graph.add_edge("classify_intent", "retrieve_knowledge")
        graph.add_edge("retrieve_knowledge", "evaluate_retrieved_context")
        graph.add_edge("evaluate_retrieved_context", "generate_answer")
        graph.add_edge("generate_answer", "calculate_confidence")
        graph.add_edge("calculate_confidence", "decision")

        def route_after_decision(s: SupportAgentState) -> str:
            if s.decision == AgentDecision.AI_RESOLVE:
                return "finalize_response"
            return END

        graph.add_conditional_edges("decision", route_after_decision, {"finalize_response": "finalize_response", END: END})
        graph.add_edge("finalize_response", END)

        app = graph.compile()
        result = await app.ainvoke(state)
        if isinstance(result, SupportAgentState):
            return result
        return SupportAgentState.model_validate(result)
    except Exception:
        return await _fallback_support_agent(state, config=config, llm=provider, retriever=retriever, db_session=db_session)


async def _generate_answer(provider: LLMProvider, prompt: str, state: SupportAgentState) -> GeneratedAnswer:
    try:
        return await provider.structured_output(prompt, GeneratedAnswer)
    except Exception:
        text = await provider.generate(prompt)
        grounded = bool(state.retrieved_documents) and state.retrieval_score >= get_settings().ai_min_retrieval_score
        return GeneratedAnswer(answer=text, grounded=grounded)


async def _fallback_support_agent(
    state: SupportAgentState,
    *,
    config: AIConfig,
    llm: LLMProvider,
    retriever: Retriever | None,
    db_session: Any,
) -> SupportAgentState:
    settings = get_settings()
    state.human_requested = detect_human_request(state.user_message)
    classification = await run_classification_graph(state.user_message, llm=llm)
    state.intent = classification.intent
    state.intent_confidence = classification.confidence
    state.sentiment = classification.sentiment
    state.human_requested = state.human_requested or classification.requires_human

    if db_session and state.organization_id:
        store = retriever or PgVectorRetriever(db_session)
        hits = await store.search(
            state.user_message, organization_id=state.organization_id, top_k=settings.ai_retrieval_top_k
        )
        ranked = await Reranker(llm=llm).rank(state.user_message, hits, top_k=settings.ai_final_top_k)
        state.retrieved_documents = [
            RetrievedDocument(
                document_id=r.hit.document_id,
                title=r.hit.title,
                content=r.hit.content,
                score=r.relevance,
                chunk_id=r.hit.chunk_id,
            )
            for r in ranked
        ]
        state.retrieval_score = aggregate_retrieval_score(ranked)

    answer = await _generate_answer(llm, render_generate_prompt(state), state)
    state.draft_response = answer.answer
    state.grounded = answer.grounded and bool(state.retrieved_documents)
    state.citations = [
        Citation(document_id=d.document_id, title=d.title, chunk_id=d.chunk_id)
        for d in state.retrieved_documents[:3]
    ]
    state.support_confidence = calculate_support_confidence(state)
    state = evaluate_escalation(state, config)
    if state.decision == AgentDecision.AI_RESOLVE:
        state.final_response = state.draft_response
    else:
        state.escalation_summary = await llm.generate(render_escalation_summary_prompt(state))
    return state


async def timed_support_agent(
    state: SupportAgentState,
    *,
    config: AIConfig,
    llm: LLMProvider | None = None,
    retriever: Retriever | None = None,
    db_session: Any = None,
) -> tuple[SupportAgentState, int]:
    started = time.perf_counter()
    result = await run_support_agent_graph(
        state, config=config, llm=llm, retriever=retriever, db_session=db_session
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return result, latency_ms


GRAPH_VERSION = PROMPT_VERSION
