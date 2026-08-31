"""Build conversation + customer context for the support agent."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.infrastructure.database.models import Conversation, Customer, Message, SenderType
from app.modules.ai.domain.schemas import ConversationTurn, CustomerContext, SupportAgentState


def _sender_label(sender_type: SenderType) -> str:
    if sender_type == SenderType.CUSTOMER:
        return "Customer"
    if sender_type == SenderType.AI:
        return "AI Support"
    if sender_type == SenderType.AGENT:
        return "Agent"
    return sender_type.value.title()


def format_history_for_prompt(turns: list[ConversationTurn]) -> str:
    if not turns:
        return "(no prior messages)"
    lines = [f"{_sender_label(SenderType(t.sender_type))}: {t.content}" for t in turns]
    return "\n".join(lines)


class ContextBuilder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def build(
        self,
        conversation_id: str,
        message_id: str | None = None,
    ) -> SupportAgentState:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        customer = conversation.customer
        if customer is None:
            cust_result = await self.db.execute(
                select(Customer).where(Customer.id == conversation.customer_id)
            )
            customer = cust_result.scalar_one()

        msgs_result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        all_messages = list(msgs_result.scalars().all())

        if message_id:
            target = next((m for m in all_messages if m.id == message_id), None)
            if target is None:
                raise ValueError(f"Message {message_id} not found in conversation")
            prior = [m for m in all_messages if m.created_at <= target.created_at and m.id != message_id]
            user_message = target.content
        else:
            prior = all_messages[:-1] if all_messages else []
            user_message = all_messages[-1].content if all_messages else ""

        limit = self.settings.ai_context_message_limit
        recent = prior[-limit:] if limit else prior

        history = [
            ConversationTurn(sender_type=m.sender_type.value, content=m.content) for m in recent
        ]

        return SupportAgentState(
            conversation_id=conversation_id,
            message_id=message_id,
            organization_id=conversation.organization_id,
            customer_context=CustomerContext(
                customer_id=customer.id,
                name=customer.name,
                email=customer.email,
                company=customer.company_name,
                metadata=dict(customer.metadata_ or {}),
            ),
            conversation_history=history,
            user_message=user_message,
        )
