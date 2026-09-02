"""Day 6 loop protection tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Customer, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.automation.application.execution_service import ExecutionService, MAX_EXECUTION_DEPTH
from app.modules.automation.domain.models import Automation


@pytest.mark.asyncio
async def test_execution_depth_limit_stops_cascade() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Loop")
        session.add(customer)
        await session.flush()

        session.add(
            Automation(
                organization_id=org_id,
                name="Loop Test",
                enabled=True,
                trigger={"type": "CONVERSATION_ASSIGNED"},
                conditions=None,
                actions=[{"type": "SET_PRIORITY", "value": "HIGH"}],
                priority=1,
            )
        )
        await session.flush()

        results = await ExecutionService(session).execute_for_event(
            organization_id=org_id,
            event_name="conversation.assigned",
            payload={"conversation_id": "none", "customer_id": customer.id},
            execution_depth=MAX_EXECUTION_DEPTH,
        )
        assert results == []
