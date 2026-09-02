"""Tag management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tags.domain.models import ConversationTag, Tag, TicketTag


class TagService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_tag(self, organization_id: str, name: str) -> Tag:
        normalized = name.strip().lower()
        tag = await self.db.scalar(
            select(Tag).where(Tag.organization_id == organization_id, Tag.name == normalized)
        )
        if tag is None:
            tag = Tag(organization_id=organization_id, name=normalized)
            self.db.add(tag)
            await self.db.flush()
        return tag

    async def add_conversation_tag(self, organization_id: str, conversation_id: str, tag_name: str) -> bool:
        tag = await self.get_or_create_tag(organization_id, tag_name)
        existing = await self.db.scalar(
            select(ConversationTag).where(
                ConversationTag.conversation_id == conversation_id,
                ConversationTag.tag_id == tag.id,
            )
        )
        if existing is not None:
            return False
        self.db.add(ConversationTag(conversation_id=conversation_id, tag_id=tag.id))
        await self.db.flush()
        return True

    async def remove_conversation_tag(self, organization_id: str, conversation_id: str, tag_name: str) -> bool:
        tag = await self.db.scalar(
            select(Tag).where(Tag.organization_id == organization_id, Tag.name == tag_name.strip().lower())
        )
        if tag is None:
            return False
        row = await self.db.scalar(
            select(ConversationTag).where(
                ConversationTag.conversation_id == conversation_id,
                ConversationTag.tag_id == tag.id,
            )
        )
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def list_conversation_tags(self, conversation_id: str) -> list[str]:
        result = await self.db.execute(
            select(Tag.name)
            .join(ConversationTag, ConversationTag.tag_id == Tag.id)
            .where(ConversationTag.conversation_id == conversation_id)
        )
        return [row[0] for row in result.all()]
