"""Day 5 email threading tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Message, Organization, User
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.email import get_mock_email_provider
from app.main import app
from app.modules.channels.schemas import EmailSendRequest
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_email_thread_stays_same_conversation() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        agent = (await session.execute(select(User).limit(1))).scalar_one()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload1 = {
            "organization_id": org_id,
            "message_id": "<thread-root@example.com>",
            "from_email": "threader@example.com",
            "subject": "API Error",
            "body_text": "My API calls fail.",
        }
        r1 = await client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload1,
            headers={"x-mock-signature": "test-bypass"},
        )
        assert r1.status_code == 200
        conv_id = r1.json()["conversation_id"]

    async with AsyncSessionLocal() as session:
        agent = (await session.execute(select(User).limit(1))).scalar_one()
        await ConversationService(session).send_email_reply(
            agent,
            conv_id,
            EmailSendRequest(content="We are investigating.", subject="Re: API Error"),
        )
        outbound = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conv_id, Message.external_message_id.is_not(None))
                .order_by(Message.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        await session.commit()
        outbound_id = outbound.external_message_id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload2 = {
            "organization_id": org_id,
            "message_id": "<thread-reply@example.com>",
            "from_email": "threader@example.com",
            "subject": "Re: API Error",
            "body_text": "Still failing after your fix.",
            "in_reply_to": outbound_id,
        }
        r2 = await client.post(
            "/api/v1/webhooks/email/inbound",
            json=payload2,
            headers={"x-mock-signature": "test-bypass"},
        )
        assert r2.status_code == 200
        assert r2.json()["conversation_id"] == conv_id

    async with AsyncSessionLocal() as session:
        conv_count = (
            await session.execute(
                select(Conversation).where(Conversation.id == conv_id)
            )
        ).scalar_one()
        assert conv_count.channel.value == "EMAIL"
        msgs = (
            await session.execute(select(Message).where(Message.conversation_id == conv_id))
        ).scalars().all()
        assert len(msgs) >= 3

    get_mock_email_provider().sent.clear()
