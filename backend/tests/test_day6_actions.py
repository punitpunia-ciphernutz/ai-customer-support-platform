"""Day 6 action handler tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Customer, Organization, Priority, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.automation.application.action_service import execute_action
from app.modules.automation.application.context_builder import AutomationContext
from app.modules.automation.domain.enums import ActionType
from app.modules.notifications.application.service import NotificationService
from app.modules.notifications.domain.models import Notification


@pytest.mark.asyncio
async def test_notify_team_resolves_team_name() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Notify Test")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT")
        session.add(conv)
        await session.flush()

        ctx = AutomationContext(organization_id=org_id, conversation_id=conv.id, customer_id=customer.id)
        result = await execute_action(
            session,
            ctx,
            {"type": ActionType.NOTIFY_TEAM.value, "value": "Billing"},
        )
        await session.commit()

        assert result["notified"] >= 1
        note = await session.scalar(select(Notification).where(Notification.user_id == user.id))
        assert note is not None


@pytest.mark.asyncio
async def test_set_priority_starts_sla_timers() -> None:
    from app.modules.sla.domain.models import SLATimer

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="SLA Action")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT", priority=Priority.NORMAL)
        session.add(conv)
        await session.flush()

        ctx = AutomationContext(organization_id=org_id, conversation_id=conv.id)
        await execute_action(session, ctx, {"type": ActionType.SET_PRIORITY.value, "value": "HIGH"})
        await session.commit()

        timers = list(
            (await session.execute(select(SLATimer).where(SLATimer.conversation_id == conv.id))).scalars()
        )
        assert len(timers) >= 1
