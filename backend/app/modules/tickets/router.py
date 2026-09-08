from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import ActorType, Conversation, Ticket, TicketStatus, User
from app.infrastructure.database.session import get_db
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.auth.permissions import TICKETS_READ, TICKETS_WRITE
from app.modules.tags.application.service import TagService
from app.modules.tags.domain.models import Tag, TicketTag
from app.modules.teams.access import is_org_admin, ticket_visible_to_user, user_team_ids
from app.modules.tickets.schemas import TicketCreate, TicketOut, TicketUpdate
from app.modules.tickets.serialize import ticket_to_out

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    view: str = Query(default="all"),
    tag: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> list[TicketOut]:
    # Ensure role loaded for admin check
    if user.role is None:
        loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role)))
        if loaded:
            user = loaded

    if view == "all" and not is_org_admin(user):
        raise HTTPException(status_code=403, detail="Only owners and admins can list all tickets")

    stmt = select(Ticket).where(Ticket.organization_id == user.organization_id)
    if view == "mine":
        stmt = stmt.where(Ticket.assigned_user_id == user.id)
    elif view == "team":
        team_ids = await user_team_ids(db, user.id)
        stmt = stmt.where(
            or_(
                Ticket.assigned_team_id.in_(team_ids or ["__none__"]),
                Ticket.assigned_user_id == user.id,
            )
        )
    elif view == "unassigned":
        stmt = stmt.where(Ticket.assigned_team_id.is_(None))
    elif view != "all":
        raise HTTPException(status_code=400, detail="Invalid view")

    tag_filters = [t.strip().lower() for t in (tag or []) if t and t.strip()]
    if tag_filters:
        for tag_name in tag_filters:
            stmt = stmt.where(
                Ticket.id.in_(
                    select(TicketTag.ticket_id)
                    .join(Tag, Tag.id == TicketTag.tag_id)
                    .where(Tag.organization_id == user.organization_id, Tag.name == tag_name)
                )
            )

    stmt = stmt.order_by(Ticket.created_at.desc())
    result = await db.execute(stmt)
    tickets = list(result.scalars().all())
    tag_map = await TagService(db).map_ticket_tags([t.id for t in tickets])
    return [ticket_to_out(t, tag_map.get(t.id, [])) for t in tickets]


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> TicketOut:
    conv = await db.execute(
        select(Conversation).where(
            Conversation.id == body.conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    conversation = conv.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from app.modules.assignment.application.service import AssignmentService

    team_id = body.assigned_team_id or conversation.assigned_team_id
    assignment = AssignmentService(db)

    if body.assigned_user_id is not None:
        ticket = Ticket(
            organization_id=user.organization_id,
            conversation_id=conversation.id,
            status=TicketStatus.OPEN,
            priority=body.priority,
            assigned_user_id=body.assigned_user_id,
            assigned_team_id=team_id,
        )
        db.add(ticket)
        await db.flush()
        await assignment.sync_manual_assignment(
            user.organization_id,
            conversation_id=conversation.id,
            assigned_team_id=team_id,
            assigned_user_id=body.assigned_user_id,
            ticket=ticket,
            sync_linked_tickets=True,
        )
    elif team_id:
        ticket = Ticket(
            organization_id=user.organization_id,
            conversation_id=conversation.id,
            status=TicketStatus.OPEN,
            priority=body.priority,
            assigned_team_id=team_id,
        )
        db.add(ticket)
        await db.flush()
        await assignment.ensure_assignee_for_team(
            user.organization_id,
            team_id,
            conversation_id=conversation.id,
            ticket=ticket,
            sync_linked_tickets=True,
        )
    else:
        ticket = Ticket(
            organization_id=user.organization_id,
            conversation_id=conversation.id,
            status=TicketStatus.OPEN,
            priority=body.priority,
            assigned_user_id=body.assigned_user_id,
            assigned_team_id=body.assigned_team_id,
        )
        db.add(ticket)
        await db.flush()

    await db.refresh(ticket)
    await write_audit(
        db,
        organization_id=user.organization_id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        action="ticket.created",
        entity_type="ticket",
        entity_id=ticket.id,
        new_value={"conversation_id": conversation.id, "status": ticket.status.value},
    )
    await event_bus.publish(
        DomainEvent(
            name="ticket.created",
            organization_id=user.organization_id,
            payload={"ticket_id": ticket.id, "conversation_id": conversation.id},
        )
    )
    # Inherit conversation tags onto the new ticket so tags stay aligned.
    service = TagService(db)
    for tag_name in await service.list_conversation_tags(conversation.id):
        await service.add_ticket_tag(user.organization_id, ticket.id, tag_name)
    tags = await service.list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> TicketOut:
    ticket = await _get_ticket(db, user, ticket_id)
    tags = await TagService(db).list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> TicketOut:
    ticket = await _get_ticket(db, user, ticket_id)
    old = {
        "status": ticket.status.value,
        "assigned_user_id": ticket.assigned_user_id,
        "priority": ticket.priority.value,
    }
    data = body.model_dump(exclude_unset=True)
    team_in_payload = "assigned_team_id" in data
    user_in_payload = "assigned_user_id" in data
    new_team_id = data.get("assigned_team_id") if team_in_payload else ticket.assigned_team_id
    team_changing = team_in_payload and data.get("assigned_team_id") != ticket.assigned_team_id

    from app.modules.assignment.application.service import AssignmentService

    assignment = AssignmentService(db)

    if team_changing and new_team_id and not user_in_payload:
        data.pop("assigned_team_id", None)
        for key, value in data.items():
            setattr(ticket, key, value)
        await assignment.ensure_assignee_for_team(
            user.organization_id,
            new_team_id,
            conversation_id=ticket.conversation_id,
            ticket=ticket,
            sync_linked_tickets=True,
        )
    elif (team_changing or user_in_payload) and ticket.conversation_id:
        for key, value in data.items():
            setattr(ticket, key, value)
        await assignment.sync_manual_assignment(
            user.organization_id,
            conversation_id=ticket.conversation_id,
            assigned_team_id=ticket.assigned_team_id,
            assigned_user_id=ticket.assigned_user_id,
            ticket=ticket,
            sync_linked_tickets=True,
        )
    else:
        for key, value in data.items():
            setattr(ticket, key, value)

    if ticket.status == TicketStatus.RESOLVED and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(UTC)
    if ticket.status == TicketStatus.CLOSED and ticket.closed_at is None:
        ticket.closed_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(ticket)

    if old["assigned_user_id"] != ticket.assigned_user_id:
        await write_audit(
            db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="ticket.assigned",
            entity_type="ticket",
            entity_id=ticket.id,
            old_value=old,
            new_value={
                "status": ticket.status.value,
                "assigned_user_id": ticket.assigned_user_id,
                "priority": ticket.priority.value,
            },
        )
        await event_bus.publish(
            DomainEvent(
                name="ticket.assigned",
                organization_id=user.organization_id,
                payload={"ticket_id": ticket.id},
            )
        )
    if ticket.status == TicketStatus.RESOLVED and old["status"] != TicketStatus.RESOLVED.value:
        await write_audit(
            db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="ticket.resolved",
            entity_type="ticket",
            entity_id=ticket.id,
            old_value=old,
            new_value={
                "status": ticket.status.value,
                "assigned_user_id": ticket.assigned_user_id,
                "priority": ticket.priority.value,
            },
        )
        await event_bus.publish(
            DomainEvent(
                name="ticket.resolved",
                organization_id=user.organization_id,
                payload={"ticket_id": ticket.id},
            )
        )
    tags = await TagService(db).list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


async def _get_ticket(db: AsyncSession, user: User, ticket_id: str) -> Ticket:
    if user.role is None:
        loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role)))
        if loaded:
            user = loaded
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
