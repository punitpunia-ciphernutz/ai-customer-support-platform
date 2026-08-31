"""Deterministic support confidence scoring."""

from __future__ import annotations

from app.modules.ai.domain.schemas import SupportAgentState


def calculate_support_confidence(state: SupportAgentState) -> float:
    intent_score = max(0.0, min(1.0, state.intent_confidence))
    retrieval_score = max(0.0, min(1.0, state.retrieval_score))
    grounding_score = 1.0 if state.grounded and state.citations else (0.4 if state.grounded else 0.2)
    context_score = 1.0 if state.customer_context and state.user_message else 0.5
    if state.conversation_history:
        context_score = min(1.0, context_score + 0.1)
    validation_score = 1.0 if state.draft_response.strip() else 0.0

    weights = (0.2, 0.25, 0.25, 0.15, 0.15)
    scores = (intent_score, retrieval_score, grounding_score, context_score, validation_score)
    return round(sum(w * s for w, s in zip(weights, scores, strict=True)), 4)
