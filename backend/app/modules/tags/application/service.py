"""Tag management."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Ticket
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

    async def list_org_tags(self, organization_id: str) -> list[Tag]:
        result = await self.db.execute(
            select(Tag).where(Tag.organization_id == organization_id).order_by(Tag.name)
        )
        return list(result.scalars().all())

    async def delete_org_tag(self, organization_id: str, tag_name: str) -> bool:
        """Permanently delete a tag and all conversation/ticket links for this org."""
        normalized = tag_name.strip().lower()
        tag = await self.db.scalar(
            select(Tag).where(Tag.organization_id == organization_id, Tag.name == normalized)
        )
        if tag is None:
            return False
        await self.db.execute(delete(ConversationTag).where(ConversationTag.tag_id == tag.id))
        await self.db.execute(delete(TicketTag).where(TicketTag.tag_id == tag.id))
        await self.db.delete(tag)
        await self.db.flush()
        return True

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
            .order_by(Tag.name)
        )
        return [row[0] for row in result.all()]

    async def add_ticket_tag(self, organization_id: str, ticket_id: str, tag_name: str) -> bool:
        tag = await self.get_or_create_tag(organization_id, tag_name)
        existing = await self.db.scalar(
            select(TicketTag).where(
                TicketTag.ticket_id == ticket_id,
                TicketTag.tag_id == tag.id,
            )
        )
        if existing is not None:
            return False
        self.db.add(TicketTag(ticket_id=ticket_id, tag_id=tag.id))
        await self.db.flush()
        return True

    async def remove_ticket_tag(self, organization_id: str, ticket_id: str, tag_name: str) -> bool:
        tag = await self.db.scalar(
            select(Tag).where(Tag.organization_id == organization_id, Tag.name == tag_name.strip().lower())
        )
        if tag is None:
            return False
        row = await self.db.scalar(
            select(TicketTag).where(
                TicketTag.ticket_id == ticket_id,
                TicketTag.tag_id == tag.id,
            )
        )
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def list_ticket_tags(self, ticket_id: str) -> list[str]:
        result = await self.db.execute(
            select(Tag.name)
            .join(TicketTag, TicketTag.tag_id == Tag.id)
            .where(TicketTag.ticket_id == ticket_id)
            .order_by(Tag.name)
        )
        return [row[0] for row in result.all()]

    async def map_ticket_tags(self, ticket_ids: list[str]) -> dict[str, list[str]]:
        if not ticket_ids:
            return {}
        result = await self.db.execute(
            select(TicketTag.ticket_id, Tag.name)
            .join(Tag, Tag.id == TicketTag.tag_id)
            .where(TicketTag.ticket_id.in_(ticket_ids))
            .order_by(Tag.name)
        )
        mapping: dict[str, list[str]] = defaultdict(list)
        for ticket_id, name in result.all():
            mapping[ticket_id].append(name)
        return dict(mapping)

    async def map_conversation_tags(self, conversation_ids: list[str]) -> dict[str, list[str]]:
        if not conversation_ids:
            return {}
        result = await self.db.execute(
            select(ConversationTag.conversation_id, Tag.name)
            .join(Tag, Tag.id == ConversationTag.tag_id)
            .where(ConversationTag.conversation_id.in_(conversation_ids))
            .order_by(Tag.name)
        )
        mapping: dict[str, list[str]] = defaultdict(list)
        for conversation_id, name in result.all():
            mapping[conversation_id].append(name)
        return dict(mapping)

    async def map_effective_conversation_tags(self, conversation_ids: list[str]) -> dict[str, list[str]]:
        """Union of conversation_tags and tags on tickets linked to each conversation."""
        if not conversation_ids:
            return {}
        conv_tags = await self.map_conversation_tags(conversation_ids)
        ticket_rows = await self.db.execute(
            select(Ticket.conversation_id, Ticket.id).where(Ticket.conversation_id.in_(conversation_ids))
        )
        tickets_by_conv: dict[str, list[str]] = defaultdict(list)
        all_ticket_ids: list[str] = []
        for conversation_id, ticket_id in ticket_rows.all():
            tickets_by_conv[conversation_id].append(ticket_id)
            all_ticket_ids.append(ticket_id)
        ticket_tags = await self.map_ticket_tags(all_ticket_ids)

        out: dict[str, list[str]] = {}
        for conversation_id in conversation_ids:
            names = set(conv_tags.get(conversation_id, []))
            for ticket_id in tickets_by_conv.get(conversation_id, []):
                names.update(ticket_tags.get(ticket_id, []))
            out[conversation_id] = sorted(names)
        return out

    async def sync_tag_to_conversation(self, organization_id: str, conversation_id: str, tag_name: str) -> None:
        await self.add_conversation_tag(organization_id, conversation_id, tag_name)

    async def unsync_tag_from_conversation(
        self, organization_id: str, conversation_id: str, tag_name: str
    ) -> None:
        await self.remove_conversation_tag(organization_id, conversation_id, tag_name)

    async def sync_tag_to_conversation_tickets(
        self, organization_id: str, conversation_id: str, tag_name: str
    ) -> None:
        result = await self.db.execute(select(Ticket.id).where(Ticket.conversation_id == conversation_id))
        for (ticket_id,) in result.all():
            await self.add_ticket_tag(organization_id, ticket_id, tag_name)

    async def unsync_tag_from_conversation_tickets(
        self, organization_id: str, conversation_id: str, tag_name: str
    ) -> None:
        result = await self.db.execute(select(Ticket.id).where(Ticket.conversation_id == conversation_id))
        for (ticket_id,) in result.all():
            await self.remove_ticket_tag(organization_id, ticket_id, tag_name)
