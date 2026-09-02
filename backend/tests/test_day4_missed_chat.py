"""Day 4 missed chat timeout tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    Conversation,
    ConversationStatus,
    Customer,
    Organization,
    Ticket,
    TicketSource,
    User,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.missed_chat_service import MissedChatService
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService


@pytest.mark.asyncio
async def test_missed_chat_timeout_creates_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Missed Chat")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.status = ConversationStatus.WAITING_FOR_AGENT
        conv.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        await session.flush()

        created = await MissedChatService(session).process_timeouts()
        assert created == 1

        ticket = await session.scalar(select(Ticket).where(Ticket.conversation_id == conv.id))
        assert ticket is not None
        assert ticket.source == TicketSource.MISSED_CHAT
        refreshed = await session.get(Conversation, conv.id)
        assert refreshed is not None
        assert refreshed.status == ConversationStatus.PENDING
        await session.rollback()


@pytest.mark.asyncio
async def test_recent_waiting_conversation_not_timed_out() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Recent Wait")
        session.add(customer)
        await session.flush()
        conv = await ConversationService(session).create_conversation(
            user, ConversationCreate(customer_id=customer.id, channel="WEB_CHAT")
        )
        conv.status = ConversationStatus.WAITING_FOR_AGENT
        await session.flush()

        created = await MissedChatService(session).process_timeouts()
        assert created == 0
        ticket = await session.scalar(select(Ticket).where(Ticket.conversation_id == conv.id))
        assert ticket is None
        await session.rollback()
