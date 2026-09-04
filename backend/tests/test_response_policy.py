"""Unit tests for Response Policy (no DB)."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai.application.response_policy import (
    evaluate_early_policy,
    evaluate_no_kb_policy,
    render_soft_draft,
)
from app.modules.ai.domain.schemas import MessageKind, PolicyAction, SoftRefuseKind, SupportAgentState


@dataclass
class _Cfg:
    response_policy_enabled: bool = True
    soft_reply_greetings: bool = True
    ood_soft_refuse: bool = True
    ood_escalates: bool = False
    safe_reply_min_kind_confidence: float = 0.55
    assistant_scope_summary: str = "password resets and billing"
    assistant_display_name: str = "Test Bot"


def test_greeting_safe_reply() -> None:
    state = SupportAgentState(
        user_message="Hello",
        message_kind=MessageKind.GREETING,
        message_kind_confidence=0.9,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.SAFE_REPLY
    assert d.allow_ungrounded_send
    draft = render_soft_draft(state, d, _Cfg())
    assert "Hello" in draft or "help" in draft.lower()
    assert "password resets" in draft


def test_identity_safe_reply() -> None:
    state = SupportAgentState(
        user_message="Who are you?",
        message_kind=MessageKind.IDENTITY,
        message_kind_confidence=0.95,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.SAFE_REPLY
    draft = render_soft_draft(state, d, _Cfg())
    assert "Test Bot" in draft


def test_human_request_escalates() -> None:
    state = SupportAgentState(
        user_message="Speak to a human",
        message_kind=MessageKind.HUMAN_REQUEST,
        message_kind_confidence=0.99,
        human_requested=True,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.ESCALATE


def test_ood_soft_refuse_not_confused_with_no_kb() -> None:
    state = SupportAgentState(
        user_message="Does it integrate with XYZ ERP?",
        message_kind=MessageKind.OUT_OF_DOMAIN,
        message_kind_confidence=0.9,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.SOFT_REFUSE
    assert d.soft_refuse_kind == SoftRefuseKind.OUT_OF_DOMAIN
    draft = render_soft_draft(state, d, _Cfg())
    assert "outside" in draft.lower() or "focus" in draft.lower()


def test_support_no_kb_is_insufficient_knowledge_not_ood() -> None:
    state = SupportAgentState(
        user_message="How do I reset my password?",
        message_kind=MessageKind.SUPPORT_REQUEST,
        message_kind_confidence=0.95,
        knowledge_available=False,
    )
    d = evaluate_no_kb_policy(state, _Cfg())
    assert d.action == PolicyAction.SOFT_REFUSE
    assert d.soft_refuse_kind == SoftRefuseKind.INSUFFICIENT_KNOWLEDGE
    draft = render_soft_draft(state, d, _Cfg())
    assert "knowledge base" in draft.lower()
    assert "outside what I can help" not in draft


def test_unclear_clarifies() -> None:
    state = SupportAgentState(
        user_message="help",
        message_kind=MessageKind.UNCLEAR,
        message_kind_confidence=0.8,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.CLARIFY


def test_support_request_continues() -> None:
    state = SupportAgentState(
        user_message="How do I reset my password?",
        message_kind=MessageKind.SUPPORT_REQUEST,
        message_kind_confidence=0.95,
    )
    d = evaluate_early_policy(state, _Cfg())
    assert d.action == PolicyAction.CONTINUE_SUPPORT


def test_policy_disabled_continues_or_escalates_legacy() -> None:
    cfg = _Cfg(response_policy_enabled=False)
    greeting = SupportAgentState(
        user_message="Hello",
        message_kind=MessageKind.GREETING,
        message_kind_confidence=0.9,
    )
    assert evaluate_early_policy(greeting, cfg).action == PolicyAction.CONTINUE_SUPPORT
    no_kb = SupportAgentState(
        user_message="How do I reset my password?",
        message_kind=MessageKind.SUPPORT_REQUEST,
        message_kind_confidence=0.95,
    )
    assert evaluate_no_kb_policy(no_kb, cfg).action == PolicyAction.ESCALATE


def test_ood_escalates_when_configured() -> None:
    cfg = _Cfg(ood_escalates=True, ood_soft_refuse=False)
    state = SupportAgentState(
        user_message="quantum physics joke",
        message_kind=MessageKind.OUT_OF_DOMAIN,
        message_kind_confidence=0.9,
    )
    assert evaluate_early_policy(state, cfg).action == PolicyAction.ESCALATE
