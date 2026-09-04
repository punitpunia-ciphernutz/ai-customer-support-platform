"""LangGraph support agent — context, intent, retrieval, generation, confidence, decision."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import get_settings
from app.modules.ai.application.confidence_service import calculate_confidence_breakdown
from app.modules.ai.application.conversation_summarizer import ConversationSummarizer
from app.modules.ai.application.escalation import detect_human_request, evaluate_escalation
from app.modules.ai.application.grounding_validator import GroundingValidator
from app.modules.ai.application.prompt_service import PromptService
from app.modules.ai.application.response_policy import (
    apply_policy_to_state,
    evaluate_early_policy,
    evaluate_no_kb_policy,
    render_soft_draft,
)
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.application.trace_helper import TraceCollector, trace_step
from app.modules.ai.domain.models import SentimentLabel
from app.modules.ai.domain.schemas import (
    AgentDecision,
    Citation,
    GeneratedAnswer,
    MessageKind,
    PolicyAction,
    RetrievedDocument,
    SupportAgentState,
)
from app.modules.ai.graphs.classification import run_classification_graph
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider, LLMProvider, get_llm_provider
from app.modules.ai.infrastructure.reranker import Reranker, aggregate_retrieval_score
from app.modules.ai.infrastructure.retrieval.hybrid_retriever import HybridRetriever
from app.modules.ai.infrastructure.retrieval.query_preparer import QueryPreparer
from app.modules.ai.infrastructure.retrieval.relevance_gate import RelevanceGate
from app.modules.ai.prompts import PROMPT_VERSION, render_escalation_summary_prompt
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.vectorstore.retriever import PgVectorRetriever, Retriever

logger = logging.getLogger(__name__)

_SOFT_ACTIONS = frozenset(
    {PolicyAction.SAFE_REPLY, PolicyAction.SOFT_REFUSE, PolicyAction.CLARIFY}
)


def _retriever_for_session(db_session: Any, provider: LLMProvider, retriever: Retriever | None) -> Retriever:
    if retriever is not None:
        return retriever
    embedding_provider = OfflineSemanticEmbeddingProvider() if isinstance(provider, EchoLLMProvider) else None
    return PgVectorRetriever(db_session, embedding_provider=embedding_provider)


def _coerce_state(raw: SupportAgentState | dict[str, Any]) -> SupportAgentState:
    if isinstance(raw, SupportAgentState):
        return raw
    return SupportAgentState.model_validate(raw)


async def run_support_agent_graph(
    state: SupportAgentState,
    *,
    config: RuntimeAIConfig,
    llm: LLMProvider | None = None,
    retriever: Retriever | None = None,
    db_session: Any = None,
    trace: TraceCollector | None = None,
) -> SupportAgentState:
    provider = llm or get_llm_provider()
    provider.reset_usage()
    settings = get_settings()
    collector = trace or TraceCollector()
    prompt_service = PromptService(db_session) if db_session is not None else None

    async def load_context_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "load_context"):
            if db_session is None or not s.conversation_id:
                return {}
            summarizer = ConversationSummarizer(db_session, llm=provider)
            summary = await summarizer.summarize_if_needed(s.conversation_id)
            if summary:
                return {"conversation_summary": summary}
            return {}

    async def classify_intent_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "classify_intent", input_summary=s.user_message[:120]):
            human_requested = detect_human_request(s.user_message)
            classification = await run_classification_graph(
                s.user_message,
                context={"history": [t.model_dump() for t in s.conversation_history]},
                llm=provider,
            )
            kind = classification.message_kind or MessageKind.SUPPORT_REQUEST
            return {
                "intent": classification.intent,
                "intent_confidence": classification.confidence,
                "message_kind": kind,
                "message_kind_confidence": classification.message_kind_confidence,
                "sentiment": _normalize_sentiment(classification.sentiment),
                "language": classification.language,
                "human_requested": human_requested or classification.requires_human,
            }

    async def apply_response_policy_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "apply_response_policy"):
            decision = evaluate_early_policy(s, config)
            apply_policy_to_state(s, decision)
            out: dict[str, Any] = {
                "policy_action": s.policy_action,
                "policy_allows_ungrounded_send": s.policy_allows_ungrounded_send,
                "soft_refuse_kind": s.soft_refuse_kind,
                "escalation_required": s.escalation_required,
                "escalation_reason": s.escalation_reason,
            }
            if decision.action in _SOFT_ACTIONS:
                from app.modules.ai.application.response_policy import PolicyDecision

                draft = render_soft_draft(s, decision, config)
                out.update(
                    {
                        "draft_response": draft,
                        "grounded": False,
                        "citations": [],
                        "knowledge_available": False,
                    }
                )
            return out

    async def detect_language_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "detect_language"):
            language = s.language or "en"
            return {"language": language}

    async def prepare_query_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "prepare_query"):
            return {"prepared_query": QueryPreparer.prepare(s)}

    async def retrieve_knowledge_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "retrieve_knowledge"):
            if db_session is None or not s.organization_id:
                return {"retrieved_documents": [], "retrieval_score": 0.0, "knowledge_available": False}
            hybrid = HybridRetriever(
                db_session,
                retriever=_retriever_for_session(db_session, provider, retriever),
                keyword_weight=config.hybrid_keyword_weight,
            )
            hits = await hybrid.search(s, organization_id=s.organization_id, top_k=settings.ai_retrieval_top_k)
            ranked = await Reranker(llm=provider).rank(
                s.prepared_query or s.user_message, hits, top_k=settings.ai_final_top_k
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
            gate = RelevanceGate.evaluate(
                docs,
                threshold=config.min_relevance_score,
                require_knowledge=config.require_knowledge,
            )
            return {
                "retrieved_documents": docs,
                "retrieval_score": score,
                "knowledge_available": gate.passed,
            }

    async def evaluate_retrieved_context_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "evaluate_retrieved_context"):
            gate = RelevanceGate.evaluate(
                s.retrieved_documents,
                threshold=config.min_relevance_score,
                require_knowledge=config.require_knowledge,
            )
            if gate.passed:
                return {"knowledge_available": True}

            # No KB — Response Policy decides soft refuse vs escalate (not auto-OOD)
            decision = evaluate_no_kb_policy(s, config)
            apply_policy_to_state(s, decision)
            out: dict[str, Any] = {
                "knowledge_available": False,
                "grounded": False,
                "citations": [],
                "policy_action": s.policy_action,
                "policy_allows_ungrounded_send": s.policy_allows_ungrounded_send,
                "soft_refuse_kind": s.soft_refuse_kind,
                "escalation_required": s.escalation_required,
                "escalation_reason": s.escalation_reason,
            }
            if decision.action in _SOFT_ACTIONS:
                draft = render_soft_draft(s, decision, config)
                out["draft_response"] = draft
            else:
                out["draft_response"] = (
                    "I don't have enough information in our knowledge base to answer that confidently. "
                    f"Regarding: {s.user_message}"
                )
            return out

    async def generate_answer_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "generate_answer", input_summary=s.user_message[:120]):
            if prompt_service is not None:
                prompt, version_label = await prompt_service.render_support_agent_prompt(s)
            else:
                from app.modules.ai.prompts.support_agent_v1 import render_generate_prompt

                prompt = render_generate_prompt(s)
                version_label = PROMPT_VERSION
            answer = await _generate_answer(provider, prompt, s)
            citations = [
                Citation(document_id=d.document_id, title=d.title, chunk_id=d.chunk_id)
                for d in s.retrieved_documents[:3]
                if d.score >= config.min_relevance_score
            ]
            grounded = answer.grounded and bool(citations)
            draft = answer.answer
            if answer.needs_clarification and not grounded:
                draft = answer.answer
            return {
                "draft_response": draft,
                "grounded": grounded,
                "citations": citations,
                "prompt_version": version_label,
            }

    async def grounding_check_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "grounding_check"):
            if not s.draft_response:
                return {"grounded": False, "grounding_score": 0.0}
            validator = GroundingValidator(provider)
            if prompt_service is not None:
                knowledge_text = "\n\n".join(
                    f"### {d.title}\n{d.content[:800]}" for d in s.retrieved_documents
                )
                prompt = await prompt_service.render_grounding_prompt(s.draft_response, knowledge_text)
                result = await validator.validate_with_prompt(
                    prompt, s.draft_response, s.citations, source_contents=s.retrieved_documents
                )
            else:
                result = await validator.validate(
                    s.draft_response, s.citations, source_contents=s.retrieved_documents
                )
            grounded = result.grounded and result.score >= 0.5
            return {"grounded": grounded, "grounding_score": result.score}

    async def calculate_confidence_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "calculate_confidence"):
            breakdown = calculate_confidence_breakdown(s, config)
            return {
                "support_confidence": breakdown.final,
                "confidence_breakdown": breakdown,
            }

    async def decision_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "decision"):
            merged = evaluate_escalation(s, config)
            if merged.decision == AgentDecision.AI_RESOLVE:
                return {
                    "escalation_required": False,
                    "decision": AgentDecision.AI_RESOLVE,
                    "final_response": merged.draft_response,
                }
            if merged.decision == AgentDecision.SOFT_REPLY:
                return {
                    "escalation_required": False,
                    "decision": AgentDecision.SOFT_REPLY,
                    "final_response": merged.draft_response,
                    "escalation_reason": None,
                }
            if merged.decision == AgentDecision.SUGGEST_ONLY:
                return {
                    "escalation_required": False,
                    "decision": AgentDecision.SUGGEST_ONLY,
                    "final_response": merged.draft_response,
                }
            summary_prompt = render_escalation_summary_prompt(merged)
            summary = await provider.generate(summary_prompt)
            return {
                "escalation_required": True,
                "escalation_reason": merged.escalation_reason,
                "decision": AgentDecision.ESCALATE,
                "escalation_summary": summary[:2000],
                "final_response": None,
            }

    async def finalize_response_node(raw: SupportAgentState | dict[str, Any]) -> dict[str, Any]:
        s = _coerce_state(raw)
        async with trace_step(collector, "finalize_response"):
            return {"final_response": s.draft_response}

    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(SupportAgentState)
        graph.add_node("load_context", load_context_node)
        graph.add_node("classify_intent", classify_intent_node)
        graph.add_node("apply_response_policy", apply_response_policy_node)
        graph.add_node("detect_language", detect_language_node)
        graph.add_node("prepare_query", prepare_query_node)
        graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
        graph.add_node("evaluate_retrieved_context", evaluate_retrieved_context_node)
        graph.add_node("generate_answer", generate_answer_node)
        graph.add_node("grounding_check", grounding_check_node)
        graph.add_node("calculate_confidence", calculate_confidence_node)
        graph.add_node("decision", decision_node)
        graph.add_node("finalize_response", finalize_response_node)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "classify_intent")
        graph.add_edge("classify_intent", "apply_response_policy")

        def route_after_policy(s: SupportAgentState) -> str:
            action = s.policy_action
            if action in _SOFT_ACTIONS:
                return "calculate_confidence"
            if action == PolicyAction.ESCALATE:
                return "calculate_confidence"
            return "detect_language"

        graph.add_conditional_edges(
            "apply_response_policy",
            route_after_policy,
            {
                "calculate_confidence": "calculate_confidence",
                "detect_language": "detect_language",
            },
        )
        graph.add_edge("detect_language", "prepare_query")
        graph.add_edge("prepare_query", "retrieve_knowledge")
        graph.add_edge("retrieve_knowledge", "evaluate_retrieved_context")

        def route_after_knowledge(s: SupportAgentState) -> str:
            if s.knowledge_available is False:
                return "calculate_confidence"
            return "generate_answer"

        graph.add_conditional_edges(
            "evaluate_retrieved_context",
            route_after_knowledge,
            {"generate_answer": "generate_answer", "calculate_confidence": "calculate_confidence"},
        )
        graph.add_edge("generate_answer", "grounding_check")
        graph.add_edge("grounding_check", "calculate_confidence")
        graph.add_edge("calculate_confidence", "decision")

        def route_after_decision(s: SupportAgentState) -> str:
            if s.decision in {AgentDecision.AI_RESOLVE, AgentDecision.SOFT_REPLY}:
                return "finalize_response"
            return END

        graph.add_conditional_edges(
            "decision", route_after_decision, {"finalize_response": "finalize_response", END: END}
        )
        graph.add_edge("finalize_response", END)

        app = graph.compile()
        result = await app.ainvoke(state)
        final = result if isinstance(result, SupportAgentState) else SupportAgentState.model_validate(result)
        final.trace_steps = collector.steps
        if not final.prompt_version:
            final.prompt_version = PROMPT_VERSION
        return final
    except Exception as exc:
        logger.warning("LangGraph support agent failed, using fallback: %s", exc)
        return await _fallback_support_agent(
            state,
            config=config,
            llm=provider,
            retriever=retriever,
            db_session=db_session,
            trace=collector,
        )


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
    config: RuntimeAIConfig,
    llm: LLMProvider,
    retriever: Retriever | None,
    db_session: Any,
    trace: TraceCollector,
) -> SupportAgentState:
    settings = get_settings()
    prompt_service = PromptService(db_session) if db_session is not None else None

    async with trace_step(trace, "fallback_load_context"):
        if db_session and state.conversation_id:
            summarizer = ConversationSummarizer(db_session, llm=llm)
            summary = await summarizer.summarize_if_needed(state.conversation_id)
            if summary:
                state.conversation_summary = summary

    async with trace_step(trace, "fallback_classify_intent", input_summary=state.user_message[:120]):
        state.human_requested = detect_human_request(state.user_message)
        classification = await run_classification_graph(state.user_message, llm=llm)
        state.intent = classification.intent
        state.intent_confidence = classification.confidence
        state.message_kind = classification.message_kind or MessageKind.SUPPORT_REQUEST
        state.message_kind_confidence = classification.message_kind_confidence
        state.sentiment = _normalize_sentiment(classification.sentiment)
        state.language = classification.language
        state.human_requested = state.human_requested or classification.requires_human

    async with trace_step(trace, "fallback_apply_response_policy"):
        early = evaluate_early_policy(state, config)
        apply_policy_to_state(state, early)
        if early.action in _SOFT_ACTIONS:
            state.draft_response = render_soft_draft(state, early, config)
            state.grounded = False
            state.citations = []
            state.knowledge_available = False

    skip_retrieve = state.policy_action in _SOFT_ACTIONS or state.policy_action == PolicyAction.ESCALATE

    if not skip_retrieve:
        async with trace_step(trace, "fallback_detect_language"):
            state.language = state.language or "en"

        if db_session and state.organization_id:
            async with trace_step(trace, "fallback_retrieve_knowledge"):
                hybrid = HybridRetriever(
                    db_session,
                    retriever=_retriever_for_session(db_session, llm, retriever),
                    keyword_weight=config.hybrid_keyword_weight,
                )
                state.prepared_query = QueryPreparer.prepare(state)
                hits = await hybrid.search(
                    state, organization_id=state.organization_id, top_k=settings.ai_retrieval_top_k
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
                gate = RelevanceGate.evaluate(
                    state.retrieved_documents,
                    threshold=config.min_relevance_score,
                    require_knowledge=config.require_knowledge,
                )
                state.knowledge_available = gate.passed
                if not gate.passed:
                    no_kb = evaluate_no_kb_policy(state, config)
                    apply_policy_to_state(state, no_kb)
                    state.grounded = False
                    state.citations = []
                    if no_kb.action in _SOFT_ACTIONS:
                        state.draft_response = render_soft_draft(state, no_kb, config)
                    else:
                        state.draft_response = (
                            "I don't have enough information in our knowledge base to answer that confidently. "
                            f"Regarding: {state.user_message}"
                        )

        if state.knowledge_available is not False and not state.draft_response:
            async with trace_step(trace, "fallback_generate_answer"):
                if prompt_service is not None:
                    prompt, version_label = await prompt_service.render_support_agent_prompt(state)
                    state.prompt_version = version_label
                else:
                    from app.modules.ai.prompts.support_agent_v1 import render_generate_prompt

                    prompt = render_generate_prompt(state)
                    state.prompt_version = PROMPT_VERSION
                answer = await _generate_answer(llm, prompt, state)
                state.draft_response = answer.answer
                state.grounded = answer.grounded and bool(state.retrieved_documents)
                state.citations = [
                    Citation(document_id=d.document_id, title=d.title, chunk_id=d.chunk_id)
                    for d in state.retrieved_documents[:3]
                ]
            async with trace_step(trace, "fallback_grounding_check"):
                validator = GroundingValidator(llm)
                grounding = await validator.validate(
                    state.draft_response, state.citations, source_contents=state.retrieved_documents
                )
                state.grounding_score = grounding.score
                state.grounded = grounding.grounded and grounding.score >= 0.5

    async with trace_step(trace, "fallback_calculate_confidence"):
        breakdown = calculate_confidence_breakdown(state, config)
        state.support_confidence = breakdown.final
        state.confidence_breakdown = breakdown

    async with trace_step(trace, "fallback_decision"):
        state = evaluate_escalation(state, config)
        if state.decision in {AgentDecision.AI_RESOLVE, AgentDecision.SOFT_REPLY}:
            state.final_response = state.draft_response
        elif state.decision == AgentDecision.SUGGEST_ONLY:
            state.final_response = state.draft_response
            state.escalation_required = False
        else:
            state.escalation_summary = await llm.generate(render_escalation_summary_prompt(state))

    state.trace_steps = trace.steps
    if not state.prompt_version:
        state.prompt_version = PROMPT_VERSION
    return state


async def timed_support_agent(
    state: SupportAgentState,
    *,
    config: RuntimeAIConfig,
    llm: LLMProvider | None = None,
    retriever: Retriever | None = None,
    db_session: Any = None,
) -> tuple[SupportAgentState, int, dict[str, Any]]:
    started = time.perf_counter()
    provider = llm or get_llm_provider()
    provider.reset_usage()
    result = await run_support_agent_graph(
        state, config=config, llm=provider, retriever=retriever, db_session=db_session
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    token_usage = provider.usage.to_dict()
    return result, latency_ms, token_usage


GRAPH_VERSION = PROMPT_VERSION


def _normalize_sentiment(raw: str | SentimentLabel | None) -> str:
    """Validate/sanitize LLM sentiment only — never re-classify from message text."""
    if raw is None:
        return SentimentLabel.NEUTRAL.value
    value = str(raw).strip().upper()
    try:
        return SentimentLabel(value).value
    except ValueError:
        return SentimentLabel.NEUTRAL.value
