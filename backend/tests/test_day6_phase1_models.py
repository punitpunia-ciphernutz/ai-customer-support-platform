"""Day 6 Phase 1 — automation database models."""

from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.modules.automation.domain.enums import ActionType, AutomationTriggerType, ExecutionStatus
from app.modules.ai.domain.models import AgentStatus


def test_day6_migration_tables_exist() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in (
        "automations",
        "automation_executions",
        "automation_execution_steps",
        "business_hours",
        "business_hours_schedules",
        "business_holidays",
        "tags",
        "conversation_tags",
        "ticket_tags",
        "sla_policies",
        "sla_timers",
        "notifications",
        "notification_preferences",
    ):
        assert table in tables, f"Missing table: {table}"


def test_day6_enums() -> None:
    assert AutomationTriggerType.MESSAGE_RECEIVED.value == "MESSAGE_RECEIVED"
    assert ActionType.ASSIGN_TEAM.value == "ASSIGN_TEAM"
    assert ExecutionStatus.COMPLETED.value == "COMPLETED"
    assert AgentStatus.ONLINE.value == "ONLINE"
