"""Day 5 email AI suggest mode tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import ChannelType, Conversation, Customer, Message, Organization, SenderType
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
async def test_email_suggest_mode_creates_suggestion_not_send() -> None:
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
        bot.mode = AIMode.SUGGEST

        customer = Customer(organization_id=org_id, name="Suggest Email", email="suggest@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Help",
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

        suggestions = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.metadata_["suggestion"].astext == "true",
                )
            )
        ).scalars().all()
        assert len(suggestions) == 1
        ai_replies = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert len(ai_replies) == 0
        await session.rollback()
