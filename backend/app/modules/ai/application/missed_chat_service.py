"""Missed chat timeout → ticket routing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Conversation, ConversationStatus, Message, SenderType
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.availability_service import AvailabilityService
from app.modules.automation.infrastructure.scheduler import schedule_missed_chat_check
from app.modules.conversations.service import ConversationService


class MissedChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_timeouts(self) -> int:
        """Beat safety net — scan waiting conversations past timeout."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.status == ConversationStatus.WAITING_FOR_AGENT)
        )
        waiting = list(result.scalars().all())
        created = 0
        for conv in waiting:
            org_config = await get_or_create_ai_config(self.db, conv.organization_id)
            timeout = org_config.missed_chat_timeout_minutes
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout)
            updated = conv.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if updated > cutoff:
                continue
            if await self._handle_missed_chat(conv):
                created += 1
        await self.db.flush()
        return created

    async def schedule_check_if_needed(self, conversation_id: str, organization_id: str) -> None:
        availability = AvailabilityService(self.db)
        if await availability.is_agent_available(organization_id):
            return
        org_config = await get_or_create_ai_config(self.db, organization_id)
        schedule_missed_chat_check(conversation_id, organization_id, org_config.missed_chat_timeout_minutes)

    async def check_conversation(self, conversation_id: str, organization_id: str) -> bool:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return False
        if conv.assigned_user_id is not None:
            return False
        if conv.status not in {ConversationStatus.WAITING_FOR_AGENT, ConversationStatus.OPEN, ConversationStatus.PENDING}:
            return False
        availability = AvailabilityService(self.db)
        if await availability.is_agent_available(organization_id):
            return False
        return await self._handle_missed_chat(conv)

    async def _handle_missed_chat(self, conv: Conversation) -> bool:
        from app.modules.automation.application.execution_service import ExecutionService

        payload = {
            "conversation_id": conv.id,
            "customer_id": conv.customer_id,
            "event": "missed_chat",
        }
        await ExecutionService(self.db).execute_for_event(
            organization_id=conv.organization_id,
            event_name="missed_chat",
            payload=payload,
        )
        conv.status = ConversationStatus.PENDING
        await self.db.flush()
        return True

    async def route_incoming_if_ai_disabled(
        self,
        conversation_id: str,
        organization_id: str,
    ) -> None:
        """Mark conversation waiting when AI off and no agents online."""
        availability = AvailabilityService(self.db)
        if await availability.is_agent_available(organization_id):
            return
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None:
            return
        conv.status = ConversationStatus.WAITING_FOR_AGENT
        conversations = ConversationService(self.db)
        handoff = Message(
            conversation_id=conversation_id,
            sender_type=SenderType.SYSTEM,
            content="Our support team is currently offline. We will follow up as soon as possible.",
            metadata_={"internal": False, "offline_notice": True},
        )
        self.db.add(handoff)
        await self.db.flush()
        await conversations._publish_message(handoff, conv)  # noqa: SLF001
        await self.schedule_check_if_needed(conversation_id, organization_id)
