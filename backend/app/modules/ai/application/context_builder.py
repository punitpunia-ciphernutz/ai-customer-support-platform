"""Build conversation + customer context for the support agent (Day 4 v2)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.infrastructure.database.models import (
    Conversation,
    Customer,
    Message,
    SenderType,
    Ticket,
    TicketStatus,
)
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
            .options(selectinload(Conversation.customer), selectinload(Conversation.tickets))
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

        recent_limit = self.settings.ai_context_recent_message_limit
        recent = prior[-recent_limit:] if recent_limit else prior

        history = [
            ConversationTurn(sender_type=m.sender_type.value, content=m.content) for m in recent
        ]

        previous_ai = [
            m.content
            for m in reversed(prior)
            if m.sender_type == SenderType.AI and not (m.metadata_ or {}).get("internal")
        ][:3]
        previous_ai.reverse()

        ticket_context = await self._load_ticket_context(conversation)

        channel = conversation.channel
        channel_value = channel.value if hasattr(channel, "value") else channel
        control_mode = conversation.ai_control_mode
        control_value = control_mode.value if hasattr(control_mode, "value") else control_mode

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
            conversation_summary=conversation.conversation_summary,
            previous_ai_responses=previous_ai,
            ticket_context=ticket_context,
            channel=channel_value,
            ai_control_mode=control_value,
            user_message=user_message,
        )

    async def _load_ticket_context(self, conversation: Conversation) -> dict | None:
        open_statuses = {TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING}
        tickets = getattr(conversation, "tickets", None) or []
        open_ticket = next((t for t in tickets if t.status in open_statuses), None)
        if open_ticket is None:
            result = await self.db.execute(
                select(Ticket)
                .where(
                    Ticket.conversation_id == conversation.id,
                    Ticket.status.in_(list(open_statuses)),
                )
                .order_by(Ticket.created_at.desc())
                .limit(1)
            )
            open_ticket = result.scalar_one_or_none()
        if open_ticket is None:
            return None
        return {
            "ticket_id": open_ticket.id,
            "status": open_ticket.status.value,
            "priority": open_ticket.priority.value,
            "title": open_ticket.title,
            "source": open_ticket.source.value if open_ticket.source else None,
        }
