"""Team and membership management."""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import Conversation, Team, TeamMember, Ticket, User
from app.modules.teams.schemas import TeamMemberOut, TeamOut


class TeamServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class TeamService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_teams(self, organization_id: str) -> list[TeamOut]:
        count_sq = (
            select(TeamMember.team_id, func.count(TeamMember.id).label("member_count"))
            .group_by(TeamMember.team_id)
            .subquery()
        )
        result = await self.db.execute(
            select(Team, func.coalesce(count_sq.c.member_count, 0))
            .outerjoin(count_sq, Team.id == count_sq.c.team_id)
            .where(Team.organization_id == organization_id)
            .order_by(Team.name)
        )
        return [
            TeamOut(
                id=team.id,
                organization_id=team.organization_id,
                name=team.name,
                description=team.description,
                created_at=team.created_at,
                member_count=int(member_count),
            )
            for team, member_count in result.all()
        ]

    async def get_team(self, organization_id: str, team_id: str) -> Team:
        team = await self.db.scalar(
            select(Team).where(Team.id == team_id, Team.organization_id == organization_id)
        )
        if team is None:
            raise TeamServiceError(404, "Team not found")
        return team

    async def list_members(self, organization_id: str, team_id: str) -> list[TeamMemberOut]:
        await self.get_team(organization_id, team_id)
        result = await self.db.execute(
            select(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .where(TeamMember.team_id == team_id)
            .order_by(User.full_name)
        )
        return [
            TeamMemberOut(
                id=membership.id,
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=membership.created_at,
            )
            for membership, user in result.all()
        ]

    async def create_team(
        self,
        organization_id: str,
        name: str,
        description: str | None,
    ) -> Team:
        await self._ensure_unique_name(organization_id, name)
        team = Team(organization_id=organization_id, name=name.strip(), description=description)
        self.db.add(team)
        await self.db.flush()
        await self.db.refresh(team)
        return team

    async def update_team(
        self,
        organization_id: str,
        team_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        description_set: bool = False,
    ) -> Team:
        team = await self.get_team(organization_id, team_id)
        if name is not None:
            await self._ensure_unique_name(organization_id, name, exclude_team_id=team_id)
            team.name = name.strip()
        if description_set:
            team.description = description
        await self.db.flush()
        await self.db.refresh(team)
        return team

    async def delete_team(self, organization_id: str, team_id: str) -> None:
        team = await self.get_team(organization_id, team_id)
        conv_count = await self.db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.assigned_team_id == team_id)
        )
        ticket_count = await self.db.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.assigned_team_id == team_id)
        )
        if (conv_count or 0) > 0 or (ticket_count or 0) > 0:
            raise TeamServiceError(
                409,
                "Cannot delete team while conversations or tickets are assigned to it. Reassign them first.",
            )
        await self.db.execute(delete(TeamMember).where(TeamMember.team_id == team_id))
        await self.db.delete(team)
        await self.db.flush()

    async def add_member(self, organization_id: str, team_id: str, user_id: str) -> TeamMemberOut:
        await self.get_team(organization_id, team_id)
        user = await self.db.scalar(
            select(User).where(User.id == user_id, User.organization_id == organization_id)
        )
        if user is None:
            raise TeamServiceError(404, "User not found in this organization")
        if not user.is_active:
            raise TeamServiceError(409, "Cannot add inactive user to a team")

        existing = await self.db.scalar(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        if existing is not None:
            raise TeamServiceError(409, "User is already a member of this team")

        membership = TeamMember(team_id=team_id, user_id=user_id)
        self.db.add(membership)
        await self.db.flush()
        await self.db.refresh(membership)
        return TeamMemberOut(
            id=membership.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=membership.created_at,
        )

    async def remove_member(self, organization_id: str, team_id: str, user_id: str) -> None:
        team = await self.get_team(organization_id, team_id)
        membership = await self.db.scalar(
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        if membership is None:
            raise TeamServiceError(404, "Team member not found")
        if team.last_assigned_user_id == user_id:
            team.last_assigned_user_id = None
        await self.db.delete(membership)
        await self.db.flush()


    async def _ensure_unique_name(
        self,
        organization_id: str,
        name: str,
        *,
        exclude_team_id: str | None = None,
    ) -> None:
        normalized = name.strip().lower()
        result = await self.db.execute(
            select(Team).where(
                Team.organization_id == organization_id,
                func.lower(Team.name) == normalized,
            )
        )
        for existing in result.scalars().all():
            if exclude_team_id is None or existing.id != exclude_team_id:
                raise TeamServiceError(409, "A team with this name already exists in the organization")
