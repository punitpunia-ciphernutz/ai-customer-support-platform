"""Merged confidence threshold keeps the previous send/escalate outcome."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai.application.escalation import evaluate_escalation
from app.modules.ai.domain.models import AIMode
from app.modules.ai.domain.schemas import AgentDecision, SupportAgentState


@dataclass
class _Cfg:
    mode: AIMode = AIMode.AUTO_REPLY
    escalate_if_unknown: bool = False
    restricted_intents: list[str] | None = None
    allowed_intents: list[str] | None = None
    min_relevance_score: float = 0.35
    auto_reply_threshold: float = 0.85
    escalation_threshold: float = 0.85


def _state(confidence: float, *, grounded: bool = True) -> SupportAgentState:
    return SupportAgentState(
        user_message="How do I reset my password?",
        support_confidence=confidence,
        grounded=grounded,
        knowledge_available=True,
        retrieval_score=0.9,
    )


def test_equal_thresholds_auto_reply_or_escalate() -> None:
    config = _Cfg(auto_reply_threshold=0.85, escalation_threshold=0.85)

    resolved = evaluate_escalation(_state(0.85), config)
    assert resolved.decision == AgentDecision.AI_RESOLVE
    assert resolved.escalation_required is False

    escalated = evaluate_escalation(_state(0.84), config)
    assert escalated.decision == AgentDecision.ESCALATE
    assert escalated.escalation_required is True


def test_split_values_keep_the_stricter_outcome() -> None:
    higher_escalation = _Cfg(auto_reply_threshold=0.10, escalation_threshold=0.15)
    between = evaluate_escalation(_state(0.12), higher_escalation)
    assert between.decision == AgentDecision.ESCALATE

    above = evaluate_escalation(_state(0.16), higher_escalation)
    assert above.decision == AgentDecision.AI_RESOLVE

    higher_auto_reply = _Cfg(auto_reply_threshold=0.70, escalation_threshold=0.40)
    still_below_auto_reply = evaluate_escalation(_state(0.50), higher_auto_reply)
    assert still_below_auto_reply.decision == AgentDecision.ESCALATE

    confident = evaluate_escalation(_state(0.70), higher_auto_reply)
    assert confident.decision == AgentDecision.AI_RESOLVE


def test_ungrounded_answer_still_escalates_above_threshold() -> None:
    config = _Cfg(auto_reply_threshold=0.10, escalation_threshold=0.15)
    result = evaluate_escalation(_state(0.90, grounded=False), config)
    assert result.decision == AgentDecision.ESCALATE
