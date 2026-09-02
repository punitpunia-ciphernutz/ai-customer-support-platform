"""Automation execution context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Conversation, Customer, Message, Ticket
from app.modules.ai.domain.models import AIRun
from app.modules.tags.application.service import TagService


@dataclass
class AutomationContext:
    organization_id: str
    conversation_id: str | None = None
    customer_id: str | None = None
    ticket_id: str | None = None
    message_id: str | None = None
    channel: str | None = None
    status: str | None = None
    priority: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    ai_confidence: float | None = None
    assigned_team_id: str | None = None
    assigned_user_id: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_field(self, path: str) -> Any:
        if path in ("intent", "sentiment", "ai_confidence", "channel", "status", "priority"):
            return getattr(self, path)
        if path == "conversation.status":
            return self.status
        if path == "conversation.priority":
            return self.priority
        if path == "tags":
            return self.tags
        return self.metadata.get(path)


class ContextBuilder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        organization_id: str,
        payload: dict[str, Any],
        *,
        execution_depth: int = 0,
        trigger_event_id: str | None = None,
    ) -> AutomationContext:
        conversation_id = payload.get("conversation_id")
        ticket_id = payload.get("ticket_id")
        message_id = payload.get("message_id")

        ctx = AutomationContext(
            organization_id=organization_id,
            conversation_id=conversation_id,
            customer_id=payload.get("customer_id"),
            ticket_id=ticket_id,
            message_id=message_id,
            intent=payload.get("intent"),
            sentiment=payload.get("sentiment"),
            ai_confidence=payload.get("confidence") or payload.get("ai_confidence"),
            metadata={
                **payload,
                "execution_depth": execution_depth,
                "trigger_event_id": trigger_event_id,
            },
        )

        if conversation_id:
            conv = await self.db.get(Conversation, conversation_id)
            if conv:
                ctx.customer_id = ctx.customer_id or conv.customer_id
                ctx.status = conv.status.value if hasattr(conv.status, "value") else str(conv.status)
                ctx.priority = conv.priority.value if hasattr(conv.priority, "value") else str(conv.priority)
                ctx.channel = conv.channel.value if conv.channel and hasattr(conv.channel, "value") else (
                    str(conv.channel) if conv.channel else None
                )
                ctx.assigned_team_id = conv.assigned_team_id
                ctx.assigned_user_id = conv.assigned_user_id
                ctx.tags = await TagService(self.db).list_conversation_tags(conversation_id)

        if ticket_id and not conversation_id:
            ticket = await self.db.get(Ticket, ticket_id)
            if ticket:
                ctx.customer_id = ticket.customer_id
                ctx.conversation_id = ticket.conversation_id
                ctx.priority = ticket.priority.value if hasattr(ticket.priority, "value") else str(ticket.priority)
                ctx.status = ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status)

        if message_id and (not ctx.intent or not ctx.sentiment):
            run = await self.db.scalar(
                select(AIRun)
                .where(AIRun.message_id == message_id)
                .order_by(AIRun.created_at.desc())
                .limit(1)
            )
            if run:
                ctx.intent = ctx.intent or run.intent
                ctx.sentiment = ctx.sentiment or run.sentiment
                ctx.ai_confidence = ctx.ai_confidence if ctx.ai_confidence is not None else run.confidence

        if conversation_id and not ctx.intent:
            run = await self.db.scalar(
                select(AIRun)
                .where(AIRun.conversation_id == conversation_id)
                .order_by(AIRun.created_at.desc())
                .limit(1)
            )
            if run:
                ctx.intent = ctx.intent or run.intent
                ctx.sentiment = ctx.sentiment or run.sentiment
                ctx.ai_confidence = ctx.ai_confidence if ctx.ai_confidence is not None else run.confidence

        if message_id and not ctx.channel:
            msg = await self.db.get(Message, message_id)
            if msg and msg.channel:
                ctx.channel = msg.channel.value if hasattr(msg.channel, "value") else str(msg.channel)

        if ctx.customer_id is None and conversation_id:
            conv = await self.db.get(Conversation, conversation_id)
            if conv:
                ctx.customer_id = conv.customer_id

        return ctx
