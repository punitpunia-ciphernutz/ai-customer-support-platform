"""Day 6 idempotency tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Customer, Organization, Ticket
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.automation.application.action_service import execute_action
from app.modules.automation.application.context_builder import AutomationContext
from app.modules.automation.domain.enums import ActionType
from app.modules.tags.application.service import TagService


@pytest.mark.asyncio
async def test_add_tag_is_idempotent() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Idempotent")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT")
        session.add(conv)
        await session.flush()

        ctx = AutomationContext(organization_id=org_id, conversation_id=conv.id)
        action = {"type": ActionType.ADD_TAG.value, "value": "billing"}
        first = await execute_action(session, ctx, action)
        second = await execute_action(session, ctx, action)
        assert first["changed"] is True
        assert second["changed"] is False


@pytest.mark.asyncio
async def test_create_ticket_dedupes_by_conversation() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Ticket Dedupe")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT")
        session.add(conv)
        await session.flush()

        ctx = AutomationContext(organization_id=org_id, conversation_id=conv.id, customer_id=customer.id)
        action = {"type": ActionType.CREATE_TICKET.value, "config": {"title": "Test", "idempotency_key": "k1"}}
        first = await execute_action(session, ctx, action)
        second = await execute_action(session, ctx, action)
        await session.commit()

        assert first.get("ticket_id") or first.get("changed")
        assert second.get("skipped") is True
        tickets = list(
            (await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))).scalars()
        )
        assert len(tickets) == 1
