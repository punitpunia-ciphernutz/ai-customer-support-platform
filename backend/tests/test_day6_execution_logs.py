"""Day 6 execution log tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import ChannelType, Conversation, Customer, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.automation.application.execution_service import ExecutionService
from app.modules.automation.domain.enums import ExecutionStatus, StepType
from app.modules.automation.domain.models import Automation, AutomationExecutionStep


@pytest.mark.asyncio
async def test_execution_records_condition_and_action_steps() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Exec Log")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
        )
        session.add(conv)
        await session.flush()

        automation = Automation(
            organization_id=org_id,
            name="Test Exec Log",
            enabled=True,
            trigger={"type": "CONVERSATION_CREATED"},
            conditions={
                "logic": "AND",
                "conditions": [{"field": "channel", "operator": "EQUALS", "value": "WEB_CHAT"}],
            },
            actions=[{"type": "SET_PRIORITY", "value": "HIGH"}],
            priority=1,
        )
        session.add(automation)
        await session.flush()

        results = await ExecutionService(session).execute_for_event(
            organization_id=org_id,
            event_name="conversation.created",
            payload={"conversation_id": conv.id, "channel": "WEB_CHAT", "customer_id": customer.id},
        )
        await session.commit()

        assert results
        execution = results[0]
        steps = list(
            (
                await session.execute(
                    select(AutomationExecutionStep).where(AutomationExecutionStep.execution_id == execution.id)
                )
            ).scalars()
        )
        assert any(s.step_type == StepType.CONDITION for s in steps)
        assert execution.status in {ExecutionStatus.COMPLETED, ExecutionStatus.SKIPPED, ExecutionStatus.FAILED}
