"""Day 6 event bus integration tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Customer, Organization, Priority, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.automation.application.event_handler import register_automation_handlers
from app.modules.automation.domain.models import Automation, AutomationExecution
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_conversation_created_triggers_automation() -> None:
    await register_automation_handlers()
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Event Int")
        session.add(customer)
        await session.flush()

        session.add(
            Automation(
                organization_id=org_id,
                name="On Create High",
                enabled=True,
                trigger={"type": "CONVERSATION_CREATED"},
                conditions=None,
                actions=[{"type": "SET_PRIORITY", "value": "HIGH"}],
                priority=99,
            )
        )
        await session.flush()

        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT", priority=Priority.HIGH)
        )
        await session.commit()

        await event_bus.publish(
            DomainEvent(
                name="conversation.created",
                organization_id=org_id,
                payload={"conversation_id": conv.id, "customer_id": customer.id, "channel": "WEB_CHAT"},
            )
        )

        async with AsyncSessionLocal() as verify:
            row = await verify.scalar(
                select(AutomationExecution).where(AutomationExecution.entity_id == conv.id)
            )
            assert row is not None
