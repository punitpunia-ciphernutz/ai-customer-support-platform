"""Conversation and ticket assignment."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Conversation, Team, TeamMember, User
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.ai.domain.models import AgentAvailability, AgentStatus
from app.modules.automation.application.execution_context import automation_execution_depth


class AssignmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def assign_team(
        self,
        conversation_id: str,
        organization_id: str,
        team_id: str,
        *,
        allow_offline: bool = False,
    ) -> bool:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return False
        if conv.assigned_team_id == team_id:
            return False
        conv.assigned_team_id = team_id
        await self.db.flush()
        await self._publish_assigned(conv, organization_id)
        return True

    async def assign_team_by_name(
        self,
        conversation_id: str,
        organization_id: str,
        team_name: str,
        *,
        allow_offline: bool = False,
    ) -> bool:
        team = await self.db.scalar(
            select(Team).where(Team.organization_id == organization_id, Team.name.ilike(team_name))
        )
        if team is None:
            return False
        return await self.assign_team(conversation_id, organization_id, team.id, allow_offline=allow_offline)

    async def assign_user(
        self,
        conversation_id: str,
        organization_id: str,
        user_id: str,
        *,
        allow_offline: bool = False,
    ) -> bool:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return False
        if conv.assigned_user_id == user_id:
            return False
        agent = await self._get_availability(user_id)
        if agent and not self._is_eligible(agent, allow_offline):
            return False
        old_user = conv.assigned_user_id
        conv.assigned_user_id = user_id
        await self._adjust_active_count(old_user, -1)
        await self._adjust_active_count(user_id, 1)
        await self.db.flush()
        await self._publish_assigned(conv, organization_id)
        return True

    async def assign_round_robin(
        self,
        conversation_id: str,
        organization_id: str,
        team_id: str,
        *,
        allow_offline: bool = False,
        allow_away: bool = False,
    ) -> str | None:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return None
        team = await self.db.get(Team, team_id)
        if team is None:
            team = await self.db.scalar(
                select(Team).where(Team.organization_id == organization_id, Team.name.ilike(team_id))
            )
        if team is None:
            return None
        agent_id = await self.find_available_agent(team.id, allow_offline=allow_offline, allow_away=allow_away)
        if agent_id is None:
            conv.assigned_team_id = team.id
            await self.db.flush()
            await self._publish_assigned(conv, organization_id)
            return None
        await self.assign_user(conversation_id, organization_id, agent_id, allow_offline=allow_offline)
        conv.assigned_team_id = team.id
        team.last_assigned_user_id = agent_id
        await self.db.flush()
        return agent_id

    async def find_available_agent(
        self,
        team_id: str,
        *,
        allow_offline: bool = False,
        allow_away: bool = False,
    ) -> str | None:
        team = await self.db.get(Team, team_id)
        if team is None:
            return None
        members = await self.db.execute(select(TeamMember.user_id).where(TeamMember.team_id == team_id))
        user_ids = [row[0] for row in members.all()]
        if not user_ids:
            return None
        result = await self.db.execute(
            select(AgentAvailability)
            .where(AgentAvailability.user_id.in_(user_ids))
            .order_by(AgentAvailability.active_conversation_count.asc())
        )
        agents = list(result.scalars().all())
        eligible = [a for a in agents if self._is_eligible(a, allow_offline, allow_away)]
        if not eligible:
            return None
        if team.last_assigned_user_id:
            ordered = sorted(eligible, key=lambda a: (a.user_id != team.last_assigned_user_id, a.active_conversation_count))
            return ordered[0].user_id
        return eligible[0].user_id

    async def _get_availability(self, user_id: str) -> AgentAvailability | None:
        return await self.db.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user_id))

    def _is_eligible(
        self,
        agent: AgentAvailability,
        allow_offline: bool = False,
        allow_away: bool = False,
    ) -> bool:
        if agent.status == AgentStatus.ONLINE:
            return True
        if allow_away and agent.status == AgentStatus.AWAY:
            return True
        if allow_offline and agent.status == AgentStatus.OFFLINE:
            return True
        if agent.is_online and agent.status == AgentStatus.OFFLINE:
            return True
        return False

    async def _adjust_active_count(self, user_id: str | None, delta: int) -> None:
        if not user_id or delta == 0:
            return
        row = await self._get_availability(user_id)
        if row is None:
            return
        row.active_conversation_count = max(0, row.active_conversation_count + delta)
        await self.db.flush()

    async def _publish_assigned(self, conv: Conversation, organization_id: str) -> None:
        depth = automation_execution_depth.get()
        await event_bus.publish(
            DomainEvent(
                name="conversation.assigned",
                organization_id=organization_id,
                payload={
                    "conversation_id": conv.id,
                    "assigned_user_id": conv.assigned_user_id,
                    "assigned_team_id": conv.assigned_team_id,
                    "execution_depth": depth + 1,
                },
            )
        )
