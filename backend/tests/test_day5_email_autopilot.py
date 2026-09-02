"""Day 5 email autopilot tests."""

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
)
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.email import get_mock_email_provider
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
async def test_email_autopilot_sends_via_adapter() -> None:
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

        customer = Customer(organization_id=org_id, name="Auto Email", email="auto@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Password",
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

        provider = get_mock_email_provider()
        provider.sent.clear()

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
        assert ai_msgs[0].delivery_status == DeliveryStatus.SENT
        assert len(provider.sent) == 1
        await session.rollback()
