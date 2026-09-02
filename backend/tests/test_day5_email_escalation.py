"""Day 5 email escalation tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    Message,
    Organization,
    SenderType,
    Ticket,
    TicketSource,
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.domain.models import AIMode, BotConfiguration
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.knowledge.infrastructure.embeddings.provider import OfflineSemanticEmbeddingProvider


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.knowledge.infrastructure.embeddings.provider.get_embedding_provider",
        lambda: OfflineSemanticEmbeddingProvider(),
    )


@pytest.mark.asyncio
async def test_email_escalation_creates_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        bot = (
            await session.execute(
                select(BotConfiguration).where(
                    BotConfiguration.organization_id == org_id,
                    BotConfiguration.channel == ChannelType.EMAIL.value,
                )
            )
        ).scalar_one()
        bot.mode = AIMode.AUTO_REPLY

        customer = Customer(organization_id=org_id, name="Escalate Email", email="escalate@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Unknown",
        )
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer.id,
            content="I need to speak with a human agent immediately about a complex billing dispute.",
            channel=ChannelType.EMAIL,
        )
        session.add(msg)
        await session.flush()

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )

        tickets = (
            await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))
        ).scalars().all()
        assert len(tickets) == 1
        assert tickets[0].source == TicketSource.AI_ESCALATION
        assert tickets[0].customer_id == customer.id
        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 1
        assert ai_msgs[0].metadata_.get("escalation") is True
        assert "support team" in ai_msgs[0].content.lower()
        await session.rollback()
