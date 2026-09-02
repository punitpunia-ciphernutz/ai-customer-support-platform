"""Explainable confidence scoring for Day 4."""

from __future__ import annotations

from typing import Protocol

from app.modules.ai.domain.schemas import AgentDecision, ConfidenceBreakdown, ConfidenceComponents, SupportAgentState


class ConfidenceConfig(Protocol):
    enabled: bool
    mode: object
    escalation_threshold: float
    auto_reply_threshold: float
    min_relevance_score: float
    restricted_intents: list[str] | None


def _context_completeness(state: SupportAgentState) -> float:
    score = 0.5
    if state.customer_context and state.customer_context.name:
        score += 0.2
    if state.conversation_history:
        score += 0.15
    if state.conversation_summary:
        score += 0.15
    return min(1.0, score)


def _response_validation(state: SupportAgentState) -> float:
    if not (state.draft_response or state.final_response):
        return 0.0
    text = state.draft_response or state.final_response or ""
    if len(text.strip()) < 5:
        return 0.3
    return 1.0


def _policy_score(state: SupportAgentState, config: ConfidenceConfig | None) -> float:
    if state.human_requested:
        return 0.0
    if config and not config.enabled:
        return 0.0
    if state.ai_control_mode == "HUMAN_CONTROL":
        return 0.0
    return 1.0


def calculate_confidence_breakdown(
    state: SupportAgentState,
    config: ConfidenceConfig | None = None,
) -> ConfidenceBreakdown:
    weights = {
        "intent": 0.15,
        "retrieval": 0.25,
        "grounding": 0.25,
        "context": 0.10,
        "policy": 0.10,
        "response_validation": 0.15,
    }

    components = ConfidenceComponents(
        intent=state.intent_confidence,
        retrieval=state.retrieval_score,
        grounding=state.grounding_score if state.grounding_score else (0.9 if state.grounded else 0.2),
        context=_context_completeness(state),
        policy=_policy_score(state, config),
        response_validation=_response_validation(state),
    )

    final = (
        components.intent * weights["intent"]
        + components.retrieval * weights["retrieval"]
        + components.grounding * weights["grounding"]
        + components.context * weights["context"]
        + components.policy * weights["policy"]
        + components.response_validation * weights["response_validation"]
    )
    final = round(min(1.0, max(0.0, final)), 4)

    reasons: list[str] = []
    threshold = config.escalation_threshold if config else 0.85
    auto_threshold = config.auto_reply_threshold if config else 0.85

    if not state.knowledge_available:
        reasons.append("No sufficiently relevant knowledge found")
    if components.retrieval < (config.min_relevance_score if config else 0.35):
        reasons.append("Knowledge relevance below threshold")
    if not state.grounded or components.grounding < 0.5:
        reasons.append("Answer not grounded in retrieved knowledge")
    if state.human_requested:
        reasons.append("Customer requested human agent")
    if state.intent and config and config.restricted_intents:
        if state.intent.value in config.restricted_intents:
            reasons.append(f"Intent {state.intent.value} requires human handling")
    if components.policy < 1.0:
        reasons.append("Policy blocked auto-reply")

    decision = AgentDecision.AI_RESOLVE
    if reasons or final < auto_threshold:
        decision = AgentDecision.ESCALATE
    if config and getattr(config.mode, "value", config.mode) == "SUGGEST":
        decision = AgentDecision.SUGGEST_ONLY if not reasons else AgentDecision.ESCALATE

    return ConfidenceBreakdown(
        final=final,
        components=components,
        decision=decision,
        reasons=reasons,
    )


def calculate_support_confidence(state: SupportAgentState, config: ConfidenceConfig | None = None) -> float:
    """Backward-compatible final score."""
    return calculate_confidence_breakdown(state, config).final
