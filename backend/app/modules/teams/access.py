"""Shared team membership helpers for inbox / ticket scoping."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import RoleName, TeamMember, Ticket, User


def is_org_admin(user: User) -> bool:
    role = user.role.name if user.role else None
    return role in (RoleName.OWNER, RoleName.ADMIN)


async def user_team_ids(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(select(TeamMember.team_id).where(TeamMember.user_id == user_id))
    return list(result.scalars().all())


def ticket_visible_to_user(ticket: Ticket, user: User, team_ids: list[str]) -> bool:
    """OWNER/ADMIN see all; others see own assignee, own teams, or unassigned-team pool."""
    if is_org_admin(user):
        return True
    if ticket.assigned_user_id == user.id:
        return True
    if ticket.assigned_team_id is None:
        return True
    return ticket.assigned_team_id in team_ids
