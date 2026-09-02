"""Day 5 acceptance scenario 4 — Suggest → Accept → Send email."""

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
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.domain.models import AIMode, BotConfiguration
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.channels.schemas import EmailSendRequest
from app.modules.conversations.service import ConversationService
from app.modules.knowledge.infrastructure.embeddings.provider import OfflineSemanticEmbeddingProvider


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.knowledge.infrastructure.embeddings.provider.get_embedding_provider",
        lambda: OfflineSemanticEmbeddingProvider(),
    )


@pytest.mark.asyncio
async def test_email_suggest_accept_and_send() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        agent = (await session.execute(select(User).limit(1))).scalar_one()
        bot = (
            await session.execute(
                select(BotConfiguration).where(
                    BotConfiguration.organization_id == org_id,
                    BotConfiguration.channel == ChannelType.EMAIL.value,
                )
            )
        ).scalar_one()
        bot.mode = AIMode.SUGGEST

        customer = Customer(organization_id=org_id, name="Suggest Send", email="suggestsend@example.com")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            organization_id=org_id,
            customer_id=customer.id,
            channel=ChannelType.EMAIL,
            subject="Password help",
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

        suggestion = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.metadata_["suggestion"].astext == "true",
                    Message.metadata_["suggestion_status"].astext == "generated",
                )
            )
        ).scalar_one()

        service = ConversationService(session)
        await service.update_suggestion_status(
            agent, conv.id, suggestion.id, "accepted", event="suggestion.accepted"
        )

        provider = get_mock_email_provider()
        provider.sent.clear()

        outbound = await service.send_email_reply(
            agent,
            conv.id,
            EmailSendRequest(content=suggestion.content, subject="Re: Password help"),
        )

        assert outbound.delivery_status == DeliveryStatus.SENT
        assert len(provider.sent) == 1
        assert provider.sent[0].to_email == "suggestsend@example.com"
        await session.rollback()
