"""Serialize tickets with tag names for API responses."""

from __future__ import annotations

from app.infrastructure.database.models import Ticket
from app.modules.tickets.schemas import TicketOut


def ticket_to_out(ticket: Ticket, tags: list[str] | None = None) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        organization_id=ticket.organization_id,
        conversation_id=ticket.conversation_id,
        status=ticket.status,
        priority=ticket.priority,
        assigned_user_id=ticket.assigned_user_id,
        assigned_team_id=ticket.assigned_team_id,
        title=ticket.title,
        source=ticket.source.value if ticket.source is not None else None,
        description=ticket.description,
        created_at=ticket.created_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        tags=list(tags or []),
    )
