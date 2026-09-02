"""AI response timeout creates ticket when no customer-visible reply."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    AIControlMode,
    ConversationStatus,
    Customer,
    Message,
    Organization,
    SenderType,
    Ticket,
    TicketSource,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_response_timeout_service import AIResponseTimeoutService
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_ai_response_timeout_creates_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.ai_response_timeout_seconds = 60
        await session.flush()

        customer = Customer(organization_id=org_id, name="Timeout Customer")
        session.add(customer)
        await session.flush()

        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.ai_control_mode = AIControlMode.AI_CONTROL
        conv.status = ConversationStatus.OPEN
        await session.flush()

        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer.id,
            content="Hello, need help",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=90),
        )
        session.add(msg)
        await session.flush()

        result = await AIResponseTimeoutService(session).check_or_escalate(
            conv.id,
            customer.id,
            message_id=msg.id,
        )
        assert result["status"] == "ticket_created"
        assert result["ticket_id"] is not None

        ticket = await session.scalar(select(Ticket).where(Ticket.id == result["ticket_id"]))
        assert ticket is not None
        assert ticket.source == TicketSource.AUTOMATION

        await session.refresh(msg)
        assert msg.metadata_.get("timeout_ticket_id") == ticket.id
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_response_timeout_skips_when_replied() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.ai_response_timeout_seconds = 60
        await session.flush()

        customer = Customer(organization_id=org_id, name="Replied Customer")
        session.add(customer)
        await session.flush()

        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.ai_control_mode = AIControlMode.AI_CONTROL
        await session.flush()

        customer_msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer.id,
            content="Question",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=90),
        )
        session.add(customer_msg)
        await session.flush()

        ai_reply = Message(
            conversation_id=conv.id,
            sender_type=SenderType.AI,
            sender_id=None,
            content="Here is your answer",
            metadata_={"trigger_message_id": customer_msg.id},
            created_at=datetime.now(timezone.utc) - timedelta(seconds=80),
        )
        session.add(ai_reply)
        await session.flush()

        result = await AIResponseTimeoutService(session).check_or_escalate(
            conv.id,
            customer.id,
            message_id=customer_msg.id,
        )
        assert result["status"] == "responded"
        await session.rollback()
