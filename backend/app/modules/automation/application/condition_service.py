"""Condition tree evaluation."""

from __future__ import annotations

from typing import Any

from app.modules.automation.application.context_builder import AutomationContext
from app.modules.automation.domain.enums import ConditionOperator


def evaluate_conditions(context: AutomationContext, conditions: dict[str, Any] | None) -> bool:
    if not conditions:
        return True
    return _eval_group(context, conditions)


def _eval_group(context: AutomationContext, group: dict[str, Any]) -> bool:
    logic = (group.get("logic") or "AND").upper()
    items = group.get("conditions") or []
    if not items:
        return True
    results = [_eval_item(context, item) for item in items]
    if logic == "OR":
        return any(results)
    return all(results)


def _eval_item(context: AutomationContext, item: dict[str, Any]) -> bool:
    if "logic" in item or "conditions" in item:
        return _eval_group(context, item)
    field = item.get("field", "")
    operator = ConditionOperator(item.get("operator", ConditionOperator.EQUALS))
    expected = item.get("value")
    actual = context.get_field(field)
    return _compare(operator, actual, expected)


def _compare(operator: ConditionOperator, actual: Any, expected: Any) -> bool:
    if operator == ConditionOperator.IS_EMPTY:
        return actual is None or actual == "" or actual == []
    if operator == ConditionOperator.IS_NOT_EMPTY:
        return actual is not None and actual != "" and actual != []
    if operator == ConditionOperator.EQUALS:
        return _normalize(actual) == _normalize(expected)
    if operator == ConditionOperator.NOT_EQUALS:
        return _normalize(actual) != _normalize(expected)
    if operator == ConditionOperator.CONTAINS:
        return expected is not None and str(expected).lower() in str(actual or "").lower()
    if operator == ConditionOperator.NOT_CONTAINS:
        return expected is None or str(expected).lower() not in str(actual or "").lower()
    if operator == ConditionOperator.STARTS_WITH:
        return str(actual or "").lower().startswith(str(expected or "").lower())
    if operator == ConditionOperator.ENDS_WITH:
        return str(actual or "").lower().endswith(str(expected or "").lower())
    if operator == ConditionOperator.IN:
        values = expected if isinstance(expected, list) else [expected]
        return _normalize(actual) in [_normalize(v) for v in values]
    if operator == ConditionOperator.NOT_IN:
        values = expected if isinstance(expected, list) else [expected]
        return _normalize(actual) not in [_normalize(v) for v in values]
    if operator == ConditionOperator.GREATER_THAN:
        return _numeric(actual) > _numeric(expected)
    if operator == ConditionOperator.LESS_THAN:
        return _numeric(actual) < _numeric(expected)
    if operator == ConditionOperator.GREATER_OR_EQUAL:
        return _numeric(actual) >= _numeric(expected)
    if operator == ConditionOperator.LESS_OR_EQUAL:
        return _numeric(actual) <= _numeric(expected)
    return False


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return value.upper()
    return value


def _numeric(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
