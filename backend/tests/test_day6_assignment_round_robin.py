"""Day 6 round-robin assignment tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import ChannelType, Conversation, Customer, Organization, Team, TeamMember, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.domain.models import AgentAvailability, AgentStatus
from app.modules.assignment.application.service import AssignmentService


@pytest.mark.asyncio
async def test_round_robin_assigns_online_agent() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        team = await session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == "Support"))
        assert team is not None
        users = list((await session.execute(select(User).where(User.organization_id == org_id).limit(3))).scalars())
        for user in users:
            member = await session.scalar(
                select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
            )
            if member is None:
                session.add(TeamMember(team_id=team.id, user_id=user.id))
            avail = await session.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user.id))
            if avail is None:
                session.add(
                    AgentAvailability(
                        user_id=user.id,
                        organization_id=org_id,
                        status=AgentStatus.ONLINE,
                        is_online=True,
                        active_conversation_count=0,
                    )
                )
            else:
                avail.status = AgentStatus.ONLINE
                avail.is_online = True
        await session.flush()

        customer = await session.scalar(select(Customer).where(Customer.organization_id == org_id).limit(1))
        if customer is None:
            customer = Customer(organization_id=org_id, name="RR Test")
            session.add(customer)
            await session.flush()

        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.WEB_CHAT,
        )
        session.add(conv)
        await session.flush()

        agent_id = await AssignmentService(session).assign_round_robin(conv.id, org_id, team.id)
        assert agent_id is not None
        await session.refresh(conv)
        assert conv.assigned_user_id == agent_id
