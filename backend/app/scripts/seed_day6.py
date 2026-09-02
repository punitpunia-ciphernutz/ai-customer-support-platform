"""Seed default business hours, SLA policies, and automations."""

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.automation.domain.enums import ActionType, AutomationTriggerType, ConditionOperator
from app.modules.automation.domain.models import Automation
from app.modules.business_hours.domain.models import BusinessHours, BusinessHoursSchedule
from app.modules.sla.domain.models import SLAPolicy


def seed_business_hours(session: Session, organization_id: str, timezone: str = "UTC") -> BusinessHours:
    existing = session.scalar(
        select(BusinessHours).where(
            BusinessHours.organization_id == organization_id,
            BusinessHours.is_default.is_(True),
        )
    )
    if existing:
        return existing
    bh = BusinessHours(
        organization_id=organization_id,
        name="Support Hours",
        timezone=timezone,
        is_default=True,
    )
    session.add(bh)
    session.flush()
    for day in range(5):  # Mon-Fri
        session.add(
            BusinessHoursSchedule(
                business_hours_id=bh.id,
                day_of_week=day,
                open_time=time(9, 0),
                close_time=time(18, 0),
                closed=False,
            )
        )
    for day in (5, 6):  # Sat-Sun closed
        session.add(
            BusinessHoursSchedule(
                business_hours_id=bh.id,
                day_of_week=day,
                closed=True,
            )
        )
    return bh


def seed_sla_policies(session: Session, organization_id: str, business_hours_id: str | None) -> None:
    existing = session.scalar(
        select(SLAPolicy).where(SLAPolicy.organization_id == organization_id, SLAPolicy.name == "High Priority")
    )
    if existing:
        return
    session.add(
        SLAPolicy(
            organization_id=organization_id,
            name="High Priority",
            first_response_minutes=30,
            resolution_minutes=240,
            business_hours_id=business_hours_id,
            applies_to={"priority": "HIGH"},
            enabled=True,
        )
    )
    session.add(
        SLAPolicy(
            organization_id=organization_id,
            name="Urgent Priority",
            first_response_minutes=15,
            resolution_minutes=120,
            business_hours_id=business_hours_id,
            applies_to={"priority": "URGENT"},
            enabled=True,
        )
    )


def seed_default_automations(session: Session, organization_id: str) -> None:
    defaults = [
        {
            "name": "Route Billing",
            "priority": 20,
            "trigger": {"type": AutomationTriggerType.MESSAGE_RECEIVED.value},
            "conditions": {
                "logic": "AND",
                "conditions": [{"field": "intent", "operator": ConditionOperator.EQUALS.value, "value": "BILLING"}],
            },
            "actions": [
                {"type": ActionType.ASSIGN_TEAM.value, "value": "Billing"},
                {"type": ActionType.SET_PRIORITY.value, "value": "HIGH"},
                {"type": ActionType.ADD_TAG.value, "value": "billing"},
                {"type": ActionType.NOTIFY_TEAM.value, "value": "Billing"},
            ],
        },
        {
            "name": "Angry Customers",
            "priority": 30,
            "trigger": {"type": AutomationTriggerType.MESSAGE_RECEIVED.value},
            "conditions": {
                "logic": "AND",
                "conditions": [{"field": "sentiment", "operator": ConditionOperator.EQUALS.value, "value": "ANGRY"}],
            },
            "actions": [
                {"type": ActionType.SET_PRIORITY.value, "value": "URGENT"},
                {"type": ActionType.NOTIFY_MANAGER.value},
            ],
        },
        {
            "name": "AI Escalation",
            "priority": 40,
            "trigger": {"type": AutomationTriggerType.AI_ESCALATED.value},
            "conditions": None,
            "actions": [
                {"type": ActionType.NOTIFY_TEAM.value, "value": "Support"},
            ],
        },
        {
            "name": "Reopen on reply",
            "priority": 10,
            "trigger": {"type": AutomationTriggerType.MESSAGE_RECEIVED.value},
            "conditions": {
                "logic": "AND",
                "conditions": [
                    {"field": "conversation.status", "operator": ConditionOperator.EQUALS.value, "value": "CLOSED"}
                ],
            },
            "actions": [{"type": ActionType.SET_STATUS.value, "value": "OPEN"}],
        },
        {
            "name": "Missed Chat",
            "priority": 50,
            "trigger": {"type": AutomationTriggerType.MISSED_CHAT.value},
            "conditions": None,
            "actions": [
                {"type": ActionType.CREATE_TICKET.value, "config": {"title": "Missed Chat"}},
                {"type": ActionType.ASSIGN_TEAM.value, "value": "Support"},
            ],
        },
    ]
    for spec in defaults:
        exists = session.scalar(
            select(Automation).where(Automation.organization_id == organization_id, Automation.name == spec["name"])
        )
        if exists:
            continue
        session.add(
            Automation(
                organization_id=organization_id,
                name=spec["name"],
                enabled=True,
                trigger=spec["trigger"],
                conditions=spec["conditions"],
                actions=spec["actions"],
                priority=spec["priority"],
            )
        )
