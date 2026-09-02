"""Day 6 SLA timer tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Customer, Organization, Priority
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.sla.application.service import SLAService
from app.modules.sla.domain.models import SLATimer, SLATimerStatus, SLATimerType


@pytest.mark.asyncio
async def test_sla_timers_start_on_high_priority() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="SLA")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel="WEB_CHAT",
            priority=Priority.HIGH,
        )
        session.add(conv)
        await session.flush()

        timers = await SLAService(session).start_timers_for_conversation(org_id, conv.id, Priority.HIGH)
        await session.commit()

        assert len(timers) >= 1
        stored = list(
            (await session.execute(select(SLATimer).where(SLATimer.conversation_id == conv.id))).scalars()
        )
        assert any(t.type == SLATimerType.FIRST_RESPONSE for t in stored)
        assert all(t.status == SLATimerStatus.RUNNING for t in stored)


@pytest.mark.asyncio
async def test_complete_first_response() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="SLA Complete")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT", priority=Priority.HIGH)
        session.add(conv)
        await session.flush()
        await SLAService(session).start_timers_for_conversation(org_id, conv.id, Priority.HIGH)
        await SLAService(session).complete_first_response(conv.id)
        await session.commit()

        timer = await session.scalar(
            select(SLATimer).where(
                SLATimer.conversation_id == conv.id,
                SLATimer.type == SLATimerType.FIRST_RESPONSE,
            )
        )
        assert timer is not None
        assert timer.status == SLATimerStatus.COMPLETED
