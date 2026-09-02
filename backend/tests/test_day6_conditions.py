"""Day 6 condition evaluator tests."""

from app.modules.automation.application.condition_service import evaluate_conditions
from app.modules.automation.application.context_builder import AutomationContext


def test_condition_equals_intent() -> None:
    ctx = AutomationContext(organization_id="org", intent="BILLING")
    assert evaluate_conditions(ctx, {
        "logic": "AND",
        "conditions": [{"field": "intent", "operator": "EQUALS", "value": "BILLING"}],
    })


def test_condition_and_or() -> None:
    ctx = AutomationContext(organization_id="org", intent="BILLING", priority="HIGH")
    tree = {
        "logic": "OR",
        "conditions": [
            {
                "logic": "AND",
                "conditions": [
                    {"field": "intent", "operator": "EQUALS", "value": "BILLING"},
                    {"field": "priority", "operator": "EQUALS", "value": "HIGH"},
                ],
            },
            {"field": "sentiment", "operator": "EQUALS", "value": "ANGRY"},
        ],
    }
    assert evaluate_conditions(ctx, tree)
    ctx.priority = "NORMAL"
    assert not evaluate_conditions(ctx, tree)


def test_condition_in_channel() -> None:
    ctx = AutomationContext(organization_id="org", channel="EMAIL")
    assert evaluate_conditions(ctx, {
        "logic": "AND",
        "conditions": [{"field": "channel", "operator": "IN", "value": ["WEB_CHAT", "EMAIL"]}],
    })
