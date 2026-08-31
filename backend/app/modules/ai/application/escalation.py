"""Escalation policy for the support agent."""

from __future__ import annotations

import re

from app.config import get_settings
from app.modules.ai.domain.models import AIConfig
from app.modules.ai.domain.schemas import AgentDecision, IntentLabel, SupportAgentState

HUMAN_REQUEST_PATTERNS = (
    r"\bspeak to (a )?human\b",
    r"\btalk to (a )?human\b",
    r"\breal person\b",
    r"\blive agent\b",
    r"\bhuman agent\b",
    r"\brepresentative\b",
)


def detect_human_request(message: str) -> bool:
    lower = message.lower()
    return any(re.search(p, lower) for p in HUMAN_REQUEST_PATTERNS)


def evaluate_escalation(state: SupportAgentState, config: AIConfig) -> SupportAgentState:
    settings = get_settings()
    reasons: list[str] = []

    if state.human_requested or detect_human_request(state.user_message):
        reasons.append("Customer requested a human agent")

    if state.intent == IntentLabel.OTHER:
        reasons.append("Intent classified as OTHER")

    restricted = set(config.restricted_intents or [])
    if state.intent and state.intent.value in restricted:
        reasons.append(f"Intent {state.intent.value} is restricted")

    if config.allowed_intents:
        allowed = set(config.allowed_intents)
        if state.intent and state.intent.value not in allowed:
            reasons.append(f"Intent {state.intent.value} not in allowed list")

    if state.retrieval_score < settings.ai_min_retrieval_score:
        reasons.append("No sufficiently relevant knowledge found")

    if state.support_confidence < config.escalation_threshold:
        reasons.append(
            f"Support confidence {state.support_confidence:.2f} below threshold {config.escalation_threshold:.2f}"
        )

    if reasons:
        state.escalation_required = True
        state.escalation_reason = "; ".join(reasons)
        state.decision = AgentDecision.ESCALATE
    elif state.support_confidence >= config.auto_reply_threshold:
        state.escalation_required = False
        state.decision = AgentDecision.AI_RESOLVE
    else:
        state.escalation_required = True
        state.escalation_reason = "Confidence below auto-reply threshold"
        state.decision = AgentDecision.ESCALATE

    return state
