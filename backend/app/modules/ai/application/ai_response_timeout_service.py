"""Escalate to ticket when AI does not respond within configured timeout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    AIControlMode,
    Conversation,
    ConversationStatus,
    Message,
    SenderType,
    Ticket,
    TicketStatus,
)
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.escalation_service import EscalationService
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.conversations.service import ConversationService

DEFAULT_AI_RESPONSE_TIMEOUT_SECONDS = 60


class AIResponseTimeoutService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_timeouts(self) -> int:
        """Scan open AI-controlled conversations and create tickets for stale customer messages."""
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.status.in_([ConversationStatus.OPEN, ConversationStatus.PENDING]),
                Conversation.ai_control_mode == AIControlMode.AI_CONTROL,
            )
        )
        created = 0
        for conv in result.scalars().all():
            config = await RuntimeAIConfig.resolve(self.db, conv.organization_id, conv.channel)
            if not config.enabled:
                continue
            timeout_seconds = await self._timeout_seconds(conv.organization_id)
            customer_msg = await self._latest_unanswered_customer_message(conv.id)
            if customer_msg is None:
                continue
            if not self._is_past_timeout(customer_msg, timeout_seconds):
                continue
            ticket = await self._escalate_message(conv, customer_msg)
            if ticket is not None:
                created += 1
        await self.db.flush()
        return created

    async def check_or_escalate(
        self,
        conversation_id: str,
        customer_id: str,
        *,
        message_id: str | None = None,
    ) -> dict[str, str | int | None]:
        """Public status check; creates ticket when timeout elapsed and still no response."""
        conv = await self._get_customer_conversation(conversation_id, customer_id)
        config = await RuntimeAIConfig.resolve(self.db, conv.organization_id, conv.channel)
        timeout_seconds = await self._timeout_seconds(conv.organization_id)

        customer_msg = await self._get_customer_message(conv.id, message_id)
        if customer_msg is None:
            return {"status": "responded", "ticket_id": None, "timeout_seconds": timeout_seconds}

        if await self._has_customer_response(conv.id, customer_msg):
            return {"status": "responded", "ticket_id": None, "timeout_seconds": timeout_seconds}

        meta = customer_msg.metadata_ or {}
        if meta.get("timeout_ticket_id"):
            return {
                "status": "ticket_created",
                "ticket_id": meta["timeout_ticket_id"],
                "timeout_seconds": timeout_seconds,
            }

        if not self._is_past_timeout(customer_msg, timeout_seconds):
            return {"status": "pending", "ticket_id": None, "timeout_seconds": timeout_seconds}

        if not config.enabled or conv.ai_control_mode != AIControlMode.AI_CONTROL:
            return {"status": "pending", "ticket_id": None, "timeout_seconds": timeout_seconds}

        ticket = await self._escalate_message(conv, customer_msg)
        if ticket is None:
            return {"status": "responded", "ticket_id": None, "timeout_seconds": timeout_seconds}
        return {
            "status": "ticket_created",
            "ticket_id": ticket.id,
            "timeout_seconds": timeout_seconds,
        }

    async def _timeout_seconds(self, organization_id: str) -> int:
        config = await get_or_create_ai_config(self.db, organization_id)
        return getattr(config, "ai_response_timeout_seconds", None) or DEFAULT_AI_RESPONSE_TIMEOUT_SECONDS

    async def _get_customer_conversation(self, conversation_id: str, customer_id: str) -> Conversation:
        from fastapi import HTTPException

        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    async def _get_customer_message(self, conversation_id: str, message_id: str | None) -> Message | None:
        if message_id:
            msg = await self.db.get(Message, message_id)
            if msg is None or msg.conversation_id != conversation_id:
                return None
            if msg.sender_type != SenderType.CUSTOMER:
                return None
            return msg
        return await self._latest_unanswered_customer_message(conversation_id)

    async def _latest_unanswered_customer_message(self, conversation_id: str) -> Message | None:
        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_type == SenderType.CUSTOMER,
            )
            .order_by(Message.created_at.desc())
        )
        for msg in result.scalars():
            if not await self._has_customer_response(conversation_id, msg):
                return msg
        return None

    async def _has_customer_response(self, conversation_id: str, customer_msg: Message) -> bool:
        meta = customer_msg.metadata_ or {}
        if meta.get("timeout_ticket_id"):
            return True

        msg_time = customer_msg.created_at
        if msg_time.tzinfo is None:
            msg_time = msg_time.replace(tzinfo=timezone.utc)

        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.id != customer_msg.id,
                Message.created_at >= msg_time,
            )
            .order_by(Message.created_at.asc())
        )
        for message in result.scalars():
            message_meta = message.metadata_ or {}
            if message_meta.get("internal"):
                continue
            if message.sender_type in {SenderType.AGENT, SenderType.AI}:
                return True
            if message.sender_type == SenderType.SYSTEM and (
                message_meta.get("offline_notice") or message_meta.get("timeout_escalation")
            ):
                return True
        return False

    def _is_past_timeout(self, customer_msg: Message, timeout_seconds: int) -> bool:
        created = customer_msg.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        return created <= cutoff

    async def _escalate_message(self, conv: Conversation, customer_msg: Message) -> Ticket | None:
        if await self._has_customer_response(conv.id, customer_msg):
            return None

        meta = dict(customer_msg.metadata_ or {})
        if meta.get("timeout_ticket_id"):
            return await self.db.get(Ticket, meta["timeout_ticket_id"])

        open_ticket = await self.db.scalar(
            select(Ticket).where(
                Ticket.conversation_id == conv.id,
                Ticket.status.in_(
                    [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING]
                ),
            )
        )
        if open_ticket is not None:
            meta["timeout_ticket_id"] = open_ticket.id
            customer_msg.metadata_ = meta
            await self.db.flush()
            return open_ticket

        state = SupportAgentState(
            conversation_id=conv.id,
            organization_id=conv.organization_id,
            user_message=customer_msg.content,
            message_id=customer_msg.id,
            escalation_reason="AI response timeout",
            escalation_required=True,
        )
        ticket = await EscalationService(self.db).create_from_ai_timeout(
            state,
            organization_id=conv.organization_id,
            trigger_message_id=customer_msg.id,
        )
        meta["timeout_ticket_id"] = ticket.id
        customer_msg.metadata_ = meta
        conv.status = ConversationStatus.PENDING
        await self.db.flush()
        return ticket
