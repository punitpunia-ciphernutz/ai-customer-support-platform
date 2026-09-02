from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ChannelType, Conversation, Message
from app.modules.conversations.normalizer import normalize_subject


class EmailThreadingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_conversation(
        self,
        organization_id: str,
        *,
        in_reply_to: str | None,
        references: list[str],
        customer_id: str,
        subject: str,
    ) -> Conversation | None:
        header_ids = [h for h in ([in_reply_to] + list(references)) if h]
        if header_ids:
            msg_result = await self.db.execute(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.organization_id == organization_id,
                    Message.external_message_id.in_(header_ids),
                )
                .limit(1)
            )
            msg = msg_result.scalar_one_or_none()
            if msg is not None:
                conv = await self.db.get(Conversation, msg.conversation_id)
                if conv is not None:
                    return conv

        norm_subject = normalize_subject(subject)
        conv_result = await self.db.execute(
            select(Conversation).where(
                Conversation.organization_id == organization_id,
                Conversation.customer_id == customer_id,
                Conversation.channel == ChannelType.EMAIL,
                or_(
                    Conversation.thread_id == norm_subject,
                    Conversation.subject.is_not(None),
                ),
            )
            .order_by(Conversation.updated_at.desc())
        )
        for conv in conv_result.scalars().all():
            if conv.thread_id == norm_subject:
                return conv
            if conv.subject and normalize_subject(conv.subject) == norm_subject:
                return conv
        return None

    async def collect_thread_references(self, conversation_id: str) -> list[str]:
        result = await self.db.execute(
            select(Message.external_message_id)
            .where(
                Message.conversation_id == conversation_id,
                Message.external_message_id.is_not(None),
            )
            .order_by(Message.created_at.asc())
        )
        return [r for r in result.scalars().all() if r]

    def build_reply_subject(self, subject: str | None) -> str:
        if not subject:
            return "Re: Support request"
        if subject.lower().startswith("re:"):
            return subject
        return f"Re: {subject}"
