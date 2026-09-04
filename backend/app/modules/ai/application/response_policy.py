"""Deterministic Response Policy — maps MessageKind (+ context) to soft reply or support path.

LLM classifies message kind; this module does not invent product answers.
SUPPORT_REQUEST with no KB is never reclassified as OUT_OF_DOMAIN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.ai.domain.schemas import (
    MessageKind,
    PolicyAction,
    SoftRefuseKind,
    SupportAgentState,
)

_DEFAULT_SCOPE = (
    "password resets, account access, billing questions, and other topics in our help center"
)
_DEFAULT_NAME = "Support Assistant"

_SOFT_KINDS = frozenset(
    {MessageKind.GREETING, MessageKind.IDENTITY, MessageKind.SMALL_TALK}
)
_ANGRY = frozenset({"ANGRY", "NEGATIVE", "FRUSTRATED"})


class ResponsePolicyConfig(Protocol):
    response_policy_enabled: bool
    soft_reply_greetings: bool
    ood_soft_refuse: bool
    ood_escalates: bool
    safe_reply_min_kind_confidence: float
    assistant_scope_summary: str
    assistant_display_name: str


@dataclass
class PolicyDecision:
    action: PolicyAction
    allow_ungrounded_send: bool = False
    reasons: list[str] = field(default_factory=list)
    soft_refuse_kind: SoftRefuseKind | None = None


def _scope(config: ResponsePolicyConfig) -> str:
    return (config.assistant_scope_summary or "").strip() or _DEFAULT_SCOPE


def _name(config: ResponsePolicyConfig) -> str:
    return (config.assistant_display_name or "").strip() or _DEFAULT_NAME


def render_soft_draft(
    state: SupportAgentState,
    decision: PolicyDecision,
    config: ResponsePolicyConfig,
) -> str:
    scope = _scope(config)
    name = _name(config)
    kind = state.message_kind

    if decision.action == PolicyAction.CLARIFY:
        return (
            f"Happy to help. Could you share a bit more about what you need? "
            f"I can assist with {scope}."
        )

    if decision.action == PolicyAction.SOFT_REFUSE:
        if decision.soft_refuse_kind == SoftRefuseKind.INSUFFICIENT_KNOWLEDGE:
            return (
                "I don't have enough information in our knowledge base to answer that confidently. "
                f"I can help with {scope}. "
                "If you'd like, I can connect you with a human agent."
            )
        return (
            f"That's outside what I can help with. I focus on {scope}. "
            "Would you like me to connect you with a human agent?"
        )

    # SAFE_REPLY
    if kind == MessageKind.IDENTITY:
        return (
            f"I'm {name}, an AI support assistant. "
            f"I can help with {scope}. What can I help you with today?"
        )
    if kind == MessageKind.SMALL_TALK:
        return f"You're welcome! If you need anything else, I can help with {scope}."
    # GREETING default
    return f"Hello! I'm {name}. I can help with {scope}. How can I assist you today?"


def evaluate_early_policy(state: SupportAgentState, config: ResponsePolicyConfig) -> PolicyDecision:
    """Run after classification, before retrieval."""
    if not getattr(config, "response_policy_enabled", True):
        return PolicyDecision(
            action=PolicyAction.CONTINUE_SUPPORT,
            reasons=["Response policy disabled"],
        )

    if state.human_requested or state.message_kind == MessageKind.HUMAN_REQUEST:
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["Customer requested a human agent"],
        )

    sentiment = (state.sentiment or "").upper()
    if sentiment in _ANGRY:
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=[f"Customer sentiment: {sentiment}"],
        )

    kind = state.message_kind or MessageKind.SUPPORT_REQUEST
    kind_conf = float(state.message_kind_confidence or 0.0)
    min_conf = float(getattr(config, "safe_reply_min_kind_confidence", 0.55) or 0.55)

    if kind in _SOFT_KINDS and kind_conf < min_conf:
        return PolicyDecision(
            action=PolicyAction.CONTINUE_SUPPORT,
            reasons=["Message kind confidence below safe-reply threshold"],
        )

    if getattr(config, "soft_reply_greetings", True) and kind in _SOFT_KINDS:
        return PolicyDecision(
            action=PolicyAction.SAFE_REPLY,
            allow_ungrounded_send=True,
            reasons=[f"Safe reply for {kind.value}"],
        )

    if kind == MessageKind.OUT_OF_DOMAIN:
        if getattr(config, "ood_escalates", False):
            return PolicyDecision(
                action=PolicyAction.ESCALATE,
                reasons=["Out-of-domain message (ood_escalates)"],
                soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
            )
        if getattr(config, "ood_soft_refuse", True):
            return PolicyDecision(
                action=PolicyAction.SOFT_REFUSE,
                allow_ungrounded_send=True,
                reasons=["Out-of-domain soft refuse"],
                soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
            )
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["Out-of-domain without soft refuse"],
            soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
        )

    if kind == MessageKind.UNCLEAR:
        # Approved: real support asks are SUPPORT_REQUEST → continue; bare UNCLEAR → clarify
        return PolicyDecision(
            action=PolicyAction.CLARIFY,
            allow_ungrounded_send=True,
            reasons=["Unclear message — ask for clarification"],
        )

    return PolicyDecision(
        action=PolicyAction.CONTINUE_SUPPORT,
        reasons=["Continue support pipeline"],
    )


def evaluate_no_kb_policy(state: SupportAgentState, config: ResponsePolicyConfig) -> PolicyDecision:
    """After retrieval failed. Does not treat missing KB as OUT_OF_DOMAIN."""
    if not getattr(config, "response_policy_enabled", True):
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["No knowledge (policy disabled — legacy escalate)"],
            soft_refuse_kind=SoftRefuseKind.INSUFFICIENT_KNOWLEDGE,
        )

    if state.human_requested or state.message_kind == MessageKind.HUMAN_REQUEST:
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["Customer requested a human agent"],
        )

    sentiment = (state.sentiment or "").upper()
    if sentiment in _ANGRY:
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=[f"Customer sentiment: {sentiment}"],
        )

    # True OOD that somehow reached retrieval still uses OOD soft refuse — not "no KB = OOD"
    if state.message_kind == MessageKind.OUT_OF_DOMAIN:
        if getattr(config, "ood_escalates", False):
            return PolicyDecision(
                action=PolicyAction.ESCALATE,
                reasons=["Out-of-domain after retrieval (ood_escalates)"],
                soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
            )
        if getattr(config, "ood_soft_refuse", True):
            return PolicyDecision(
                action=PolicyAction.SOFT_REFUSE,
                allow_ungrounded_send=True,
                reasons=["Out-of-domain soft refuse"],
                soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
            )
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["Out-of-domain without soft refuse"],
            soft_refuse_kind=SoftRefuseKind.OUT_OF_DOMAIN,
        )

    # SUPPORT_REQUEST (or other continued kinds) with no KB — distinct from OOD
    if getattr(config, "ood_escalates", False):
        return PolicyDecision(
            action=PolicyAction.ESCALATE,
            reasons=["Support request with insufficient knowledge — escalate"],
            soft_refuse_kind=SoftRefuseKind.INSUFFICIENT_KNOWLEDGE,
        )

    if getattr(config, "ood_soft_refuse", True):
        return PolicyDecision(
            action=PolicyAction.SOFT_REFUSE,
            allow_ungrounded_send=True,
            reasons=["Support request with insufficient knowledge — soft refuse"],
            soft_refuse_kind=SoftRefuseKind.INSUFFICIENT_KNOWLEDGE,
        )

    return PolicyDecision(
        action=PolicyAction.ESCALATE,
        reasons=["Support request with insufficient knowledge — escalate"],
        soft_refuse_kind=SoftRefuseKind.INSUFFICIENT_KNOWLEDGE,
    )


def apply_policy_to_state(state: SupportAgentState, decision: PolicyDecision) -> SupportAgentState:
    state.policy_action = decision.action
    state.policy_allows_ungrounded_send = decision.allow_ungrounded_send
    state.soft_refuse_kind = decision.soft_refuse_kind
    if decision.action in {
        PolicyAction.SAFE_REPLY,
        PolicyAction.SOFT_REFUSE,
        PolicyAction.CLARIFY,
    }:
        state.escalation_required = False
        state.escalation_reason = None
    elif decision.action == PolicyAction.ESCALATE:
        state.escalation_required = True
        state.escalation_reason = "; ".join(decision.reasons) if decision.reasons else "Policy escalate"
    return state
