"""Day 4 Phase 2 — context builder and conversation memory."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Conversation, Customer, Message, Organization, SenderType
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.context_builder import ContextBuilder, format_history_for_prompt
from app.modules.ai.application.conversation_summarizer import ConversationSummarizer
from app.modules.ai.domain.schemas import ConversationTurn


@pytest.mark.asyncio
async def test_context_builder_includes_prior_ai_responses() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="John Doe", company_name="Acme Inc.")
        session.add(customer)
        await session.flush()

        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT")
        session.add(conv)
        await session.flush()

        msgs = [
            Message(conversation_id=conv.id, sender_type=SenderType.CUSTOMER, content="How do I reset my password?"),
            Message(
                conversation_id=conv.id,
                sender_type=SenderType.AI,
                content="Please reset your password from Settings → Security.",
            ),
            Message(
                conversation_id=conv.id,
                sender_type=SenderType.CUSTOMER,
                content="I tried that but it still doesn't work.",
            ),
        ]
        for m in msgs:
            session.add(m)
        await session.flush()

        state = await ContextBuilder(session).build(conv.id, msgs[-1].id)

        assert state.user_message == "I tried that but it still doesn't work."
        assert len(state.conversation_history) >= 2
        assert any("reset your password" in r for r in state.previous_ai_responses)
        assert state.customer_context is not None
        assert state.customer_context.company == "Acme Inc."
        await session.rollback()


def test_format_history_labels_senders() -> None:
    turns = [
        ConversationTurn(sender_type="CUSTOMER", content="Hello"),
        ConversationTurn(sender_type="AI", content="Hi there"),
    ]
    text = format_history_for_prompt(turns)
    assert "Customer: Hello" in text
    assert "AI Support: Hi there" in text


@pytest.mark.asyncio
async def test_summarizer_skips_short_conversations() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Jane")
        session.add(customer)
        await session.flush()
        conv = Conversation(organization_id=org_id, customer_id=customer.id, channel="WEB_CHAT")
        session.add(conv)
        await session.flush()
        session.add(Message(conversation_id=conv.id, sender_type=SenderType.CUSTOMER, content="Hi"))
        await session.flush()

        result = await ConversationSummarizer(session).summarize_if_needed(conv.id)
        assert result is None

        refreshed = await session.get(Conversation, conv.id)
        assert refreshed is not None
        assert refreshed.conversation_summary is None
        await session.rollback()
