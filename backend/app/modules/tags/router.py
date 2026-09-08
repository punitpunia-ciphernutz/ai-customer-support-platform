"""Org tag catalog and entity tag mutations."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.api.deps import require_permission
from app.infrastructure.database.models import Conversation, Ticket, User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE, TICKETS_READ, TICKETS_WRITE
from app.modules.tags.application.service import TagService
from app.modules.tags.schemas import TagNameBody, TagNamesOut, TagOut
from app.modules.teams.access import ticket_visible_to_user, user_team_ids
from app.modules.tickets.schemas import TicketOut
from app.modules.tickets.serialize import ticket_to_out
from app.modules.conversations.schemas import ConversationOut
from app.modules.conversations.serialize import conversation_to_out

router = APIRouter(tags=["tags"])


@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> list[TagOut]:
    tags = await TagService(db).list_org_tags(user.organization_id)
    return [TagOut.model_validate(t) for t in tags]


@router.delete("/tags/{tag_name}", status_code=204)
async def delete_tag(
    tag_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> None:
    deleted = await TagService(db).delete_org_tag(user.organization_id, tag_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found")


@router.get("/tickets/{ticket_id}/tags", response_model=TagNamesOut)
async def list_ticket_tags(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> TagNamesOut:
    ticket = await _get_visible_ticket(db, user, ticket_id)
    tags = await TagService(db).list_ticket_tags(ticket.id)
    return TagNamesOut(tags=tags)


@router.post("/tickets/{ticket_id}/tags", response_model=TicketOut)
async def add_ticket_tag(
    ticket_id: str,
    body: TagNameBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> TicketOut:
    ticket = await _get_visible_ticket(db, user, ticket_id)
    service = TagService(db)
    await service.add_ticket_tag(user.organization_id, ticket.id, body.name)
    await service.sync_tag_to_conversation(user.organization_id, ticket.conversation_id, body.name)
    tags = await service.list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


@router.delete("/tickets/{ticket_id}/tags/{tag_name}", response_model=TicketOut)
async def remove_ticket_tag(
    ticket_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> TicketOut:
    ticket = await _get_visible_ticket(db, user, ticket_id)
    service = TagService(db)
    removed = await service.remove_ticket_tag(user.organization_id, ticket.id, tag_name)
    if not removed:
        raise HTTPException(status_code=404, detail="Tag not found on ticket")
    await service.unsync_tag_from_conversation(user.organization_id, ticket.conversation_id, tag_name)
    tags = await service.list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


@router.get("/conversations/{conversation_id}/tags", response_model=TagNamesOut)
async def list_conversation_tags(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> TagNamesOut:
    conversation = await _get_org_conversation(db, user, conversation_id)
    tags = await TagService(db).map_effective_conversation_tags([conversation.id])
    return TagNamesOut(tags=tags.get(conversation.id, []))


@router.post("/conversations/{conversation_id}/tags", response_model=ConversationOut)
async def add_conversation_tag(
    conversation_id: str,
    body: TagNameBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await _get_org_conversation(db, user, conversation_id)
    service = TagService(db)
    await service.add_conversation_tag(user.organization_id, conversation.id, body.name)
    await service.sync_tag_to_conversation_tickets(user.organization_id, conversation.id, body.name)
    tags = await service.map_effective_conversation_tags([conversation.id])
    return conversation_to_out(conversation, tags.get(conversation.id, []))


@router.delete("/conversations/{conversation_id}/tags/{tag_name}", response_model=ConversationOut)
async def remove_conversation_tag(
    conversation_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await _get_org_conversation(db, user, conversation_id)
    service = TagService(db)
    normalized = tag_name.strip().lower()
    before = await service.map_effective_conversation_tags([conversation.id])
    if normalized not in before.get(conversation.id, []):
        raise HTTPException(status_code=404, detail="Tag not found on conversation")
    await service.remove_conversation_tag(user.organization_id, conversation.id, normalized)
    await service.unsync_tag_from_conversation_tickets(user.organization_id, conversation.id, normalized)
    tags = await service.map_effective_conversation_tags([conversation.id])
    return conversation_to_out(conversation, tags.get(conversation.id, []))


async def _ensure_role(db: AsyncSession, user: User) -> User:
    if user.role is None:
        loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role)))
        if loaded:
            return loaded
    return user


async def _get_visible_ticket(db: AsyncSession, user: User, ticket_id: str) -> Ticket:
    user = await _ensure_role(db, user)
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.organization_id == user.organization_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    team_ids = await user_team_ids(db, user.id)
    if not ticket_visible_to_user(ticket, user, team_ids):
        raise HTTPException(status_code=403, detail="Ticket is outside your team scope")
    return ticket


async def _get_org_conversation(db: AsyncSession, user: User, conversation_id: str) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
