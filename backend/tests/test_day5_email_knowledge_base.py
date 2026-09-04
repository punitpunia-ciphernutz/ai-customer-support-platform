"""Day 5 Email Knowledge Base mode on EMAIL channel."""

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
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
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
async def test_email_knowledge_base_sends_when_grounded() -> None:
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
        bot.mode = AIMode.DRAFT_ONLY

        customer = Customer(organization_id=org_id, name="KB Email", email="kbemail@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="FAQ",
        )
        session.add(conv)
        await session.flush()
        msg = Message(
            conversation_id=conv.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer.id,
            content="How do I reset my password?",
            channel=ChannelType.EMAIL,
        )
        session.add(msg)
        await session.flush()

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )

        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 1
        assert ai_msgs[0].delivery_status is not None
        await session.rollback()


@pytest.mark.asyncio
async def test_email_knowledge_base_soft_refuses_unknown() -> None:
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
        bot.mode = AIMode.DRAFT_ONLY
        cfg = await get_or_create_ai_config(session, org_id)
        cfg.response_policy_enabled = True

        customer = Customer(organization_id=org_id, name="KB Soft Email", email="kbsoft@example.com")
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
            content="Does your product integrate with XYZ?",
            channel=ChannelType.EMAIL,
        )
        session.add(msg)
        await session.flush()

        await AIService(session, llm=EchoLLMProvider()).run_support_agent(
            conv.id, msg.id, persist_side_effects=True
        )

        tickets = (await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))).scalars().all()
        assert len(tickets) == 0
        ai_msgs = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_msgs) == 1
        await session.rollback()
