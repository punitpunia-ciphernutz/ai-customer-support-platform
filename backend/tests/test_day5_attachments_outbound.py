"""Day 5 outbound attachment wiring tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    Attachment,
    ChannelType,
    Conversation,
    Customer,
    Organization,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.email import get_mock_email_provider
from app.modules.attachments.service import AttachmentService
from app.modules.channels.schemas import EmailSendRequest
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_outbound_email_includes_attachments() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        agent = (await session.execute(select(User).limit(1))).scalar_one()

        customer = Customer(organization_id=org_id, name="Attach Out", email="attachout@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Documents",
        )
        session.add(conv)
        await session.flush()

        pending = await AttachmentService(session).upload(
            organization_id=org_id,
            filename="note.txt",
            mime_type="text/plain",
            data=b"please review",
        )

        provider = get_mock_email_provider()
        provider.sent.clear()

        await ConversationService(session).send_email_reply(
            agent,
            conv.id,
            EmailSendRequest(
                content="Please see attachment.",
                subject="Re: Documents",
                attachment_ids=[pending.id],
            ),
        )

        assert len(provider.sent) == 1
        assert len(provider.sent[0].attachments) == 1
        assert provider.sent[0].attachments[0]["filename"] == "note.txt"

        linked = await session.get(Attachment, pending.id)
        assert linked is not None
        assert linked.message_id is not None
        await session.rollback()
