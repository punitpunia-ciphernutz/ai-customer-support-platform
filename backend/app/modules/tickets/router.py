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
from app.modules.teams.access import is_org_admin, ticket_visible_to_user, user_team_ids
from app.modules.tickets.schemas import TicketCreate, TicketOut, TicketUpdate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    view: str = Query(default="all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> list[Ticket]:
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

    stmt = stmt.order_by(Ticket.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> Ticket:
    conv = await db.execute(
        select(Conversation).where(
            Conversation.id == body.conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    conversation = conv.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
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
    return ticket


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_READ)),
) -> Ticket:
    return await _get_ticket(db, user, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TICKETS_WRITE)),
) -> Ticket:
    ticket = await _get_ticket(db, user, ticket_id)
    old = {
        "status": ticket.status.value,
        "assigned_user_id": ticket.assigned_user_id,
        "priority": ticket.priority.value,
    }
    data = body.model_dump(exclude_unset=True)
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
    return ticket


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
