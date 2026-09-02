"""Day 5 outbound email tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    DeliveryStatus,
    Message,
    Organization,
    SenderType,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.email import get_mock_email_provider
from app.modules.channels.schemas import EmailSendRequest
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_agent_email_reply_sends_via_provider() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        agent = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(
            organization_id=org_id,
            name="Email Customer",
            email="emailcustomer@example.com",
        )
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Billing Issue",
        )
        session.add(conv)
        await session.flush()

        provider = get_mock_email_provider()
        provider.sent.clear()

        msg = await ConversationService(session).send_email_reply(
            agent,
            conv.id,
            EmailSendRequest(content="We will review your billing.", subject="Re: Billing Issue"),
        )
        assert msg.delivery_status == DeliveryStatus.SENT
        assert msg.external_message_id
        assert len(provider.sent) == 1
        assert provider.sent[0].to_email == "emailcustomer@example.com"
        await session.rollback()
