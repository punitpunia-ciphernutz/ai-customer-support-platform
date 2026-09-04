"""Escalation policy for the support agent."""

from __future__ import annotations

import re

from typing import Protocol

from app.modules.ai.domain.models import AIMode
from app.modules.ai.domain.schemas import AgentDecision, IntentLabel, PolicyAction, SupportAgentState


class EscalationConfig(Protocol):
    mode: AIMode
    escalate_if_unknown: bool
    restricted_intents: list[str] | None
    allowed_intents: list[str] | None
    min_relevance_score: float
    escalation_threshold: float
    auto_reply_threshold: float

HUMAN_REQUEST_PATTERNS = (
    r"\bspeak to (a )?human\b",
    r"\btalk to (a )?human\b",
    r"\breal person\b",
    r"\blive agent\b",
    r"\bhuman agent\b",
    r"\brepresentative\b",
)

_SOFT_POLICY_ACTIONS = frozenset(
    {PolicyAction.SAFE_REPLY, PolicyAction.SOFT_REFUSE, PolicyAction.CLARIFY}
)


def detect_human_request(message: str) -> bool:
    lower = message.lower()
    return any(re.search(p, lower) for p in HUMAN_REQUEST_PATTERNS)


def evaluate_escalation(state: SupportAgentState, config: EscalationConfig) -> SupportAgentState:
    # Response Policy soft path — do not apply OTHER/retrieval escalate reasons
    if state.policy_allows_ungrounded_send and state.policy_action in _SOFT_POLICY_ACTIONS:
        if config.mode.value == "SUGGEST":
            state.escalation_required = False
            state.decision = AgentDecision.SUGGEST_ONLY
            state.escalation_reason = None
            return state
        state.escalation_required = False
        state.escalation_reason = None
        state.decision = AgentDecision.SOFT_REPLY
        return state

    reasons: list[str] = list(state.confidence_breakdown.reasons) if state.confidence_breakdown else []

    if state.human_requested or detect_human_request(state.user_message):
        reasons.append("Customer requested a human agent")

    if state.sentiment and state.sentiment.upper() in {"ANGRY", "NEGATIVE", "FRUSTRATED"}:
        reasons.append(f"Customer sentiment: {state.sentiment.upper()}")

    if state.intent == IntentLabel.OTHER and config.escalate_if_unknown:
        reasons.append("Intent classified as OTHER")

    restricted = set(config.restricted_intents or [])
    if state.intent and state.intent.value in restricted:
        reasons.append(f"Intent {state.intent.value} is restricted")

    if config.allowed_intents:
        allowed = set(config.allowed_intents)
        if state.intent and state.intent.value not in allowed:
            reasons.append(f"Intent {state.intent.value} not in allowed list")

    if state.retrieval_score < config.min_relevance_score:
        reasons.append("No sufficiently relevant knowledge found")

    if not state.grounded and state.knowledge_available:
        reasons.append("Answer failed grounding validation")

    if state.support_confidence < config.escalation_threshold:
        reasons.append(
            f"Support confidence {state.support_confidence:.2f} below threshold {config.escalation_threshold:.2f}"
        )

    reasons = list(dict.fromkeys(reasons))  # dedupe preserve order

    if config.mode.value == "SUGGEST":
        state.escalation_required = False
        state.decision = AgentDecision.SUGGEST_ONLY
        state.escalation_reason = None
        return state

    if reasons:
        state.escalation_required = True
        state.escalation_reason = "; ".join(reasons)
        state.decision = AgentDecision.ESCALATE
    elif state.support_confidence >= config.auto_reply_threshold and state.grounded:
        state.escalation_required = False
        state.decision = AgentDecision.AI_RESOLVE
    else:
        state.escalation_required = True
        state.escalation_reason = "Confidence or grounding below auto-reply threshold"
        state.decision = AgentDecision.ESCALATE

    return state
