"""Day 6 agent availability tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Organization, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.domain.models import AgentAvailability, AgentStatus
from app.modules.assignment.application.service import AssignmentService


@pytest.mark.asyncio
async def test_offline_agent_skipped_for_assignment() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        avail = await session.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user.id))
        assert avail is not None
        avail.status = AgentStatus.OFFLINE
        avail.is_online = False
        await session.flush()

        from app.infrastructure.database.models import ChannelType, Conversation, Customer

        customer = Customer(organization_id=org_id, name="Offline")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel=ChannelType.WEB_CHAT)
        session.add(conv)
        await session.flush()

        changed = await AssignmentService(session).assign_user(conv.id, org_id, user.id)
        assert changed is False
