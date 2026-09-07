"""Conversation and ticket assignment."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Conversation, Team, TeamMember, Ticket
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
        del allow_offline  # team assign does not use offline flags; RR uses ONLINE-only
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return False
        if conv.assigned_team_id == team_id:
            return False
        await self.ensure_assignee_for_team(
            organization_id,
            team_id,
            conversation_id=conversation_id,
            sync_linked_tickets=True,
        )
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
        allow_away: bool = False,
        skip_eligibility: bool = False,
    ) -> bool:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return False
        if conv.assigned_user_id == user_id:
            return False
        if not skip_eligibility:
            agent = await self._get_availability(user_id)
            if agent and not self._is_eligible(agent, allow_offline, allow_away):
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
        await self.assign_user(
            conversation_id,
            organization_id,
            agent_id,
            allow_offline=allow_offline,
            allow_away=allow_away,
        )
        conv.assigned_team_id = team.id
        team.last_assigned_user_id = agent_id
        await self.db.flush()
        return agent_id

    async def auto_assign_if_needed(
        self,
        conversation_id: str,
        organization_id: str,
        team_id: str | None = None,
    ) -> str | None:
        """Round-robin among ONLINE members of the conversation's current team.

        No-op if a user is already assigned. Does not fall back to other teams.
        AWAY/OFFLINE members are skipped. Returns assignee id or None.
        """
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return None
        if conv.assigned_user_id:
            return conv.assigned_user_id
        resolved_team_id = team_id or conv.assigned_team_id
        if not resolved_team_id:
            return None
        return await self.assign_round_robin(
            conversation_id,
            organization_id,
            resolved_team_id,
            allow_offline=False,
            allow_away=False,
        )

    async def ensure_assignee_for_team(
        self,
        organization_id: str,
        team_id: str,
        *,
        conversation_id: str | None = None,
        ticket: Ticket | None = None,
        sync_linked_tickets: bool = True,
        keep_assignee_if_member: bool = True,
    ) -> str | None:
        """Set current team and assign an ONLINE member of that team only.

        If the existing assignee belongs to the new team, keep them (manual-safe).
        Otherwise clear the old assignee and round-robin among ONLINE members of
        ``team_id``. Never falls back to another team. Syncs conversation + ticket(s).
        """
        if ticket is not None and conversation_id is None:
            conversation_id = ticket.conversation_id
        if not conversation_id:
            return None

        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return None

        team = await self.db.get(Team, team_id)
        if team is None or team.organization_id != organization_id:
            return None

        old_user = conv.assigned_user_id
        keep = bool(
            keep_assignee_if_member
            and old_user
            and await self._user_on_team(old_user, team_id)
        )

        conv.assigned_team_id = team_id
        assignee: str | None
        if keep:
            assignee = old_user
        else:
            if old_user:
                conv.assigned_user_id = None
                await self._adjust_active_count(old_user, -1)
            agent_id = await self.find_available_agent(team_id, allow_offline=False, allow_away=False)
            if agent_id:
                conv.assigned_user_id = agent_id
                await self._adjust_active_count(agent_id, 1)
                team.last_assigned_user_id = agent_id
                assignee = agent_id
            else:
                conv.assigned_user_id = None
                assignee = None

        await self.db.flush()
        await self._publish_assigned(conv, organization_id)
        await self._sync_tickets_with_conversation(
            conversation_id,
            team_id=team_id,
            assigned_user_id=assignee,
            primary_ticket=ticket,
            sync_linked_tickets=sync_linked_tickets,
        )
        return assignee

    async def mirror_assignment_to_ticket(self, ticket: Ticket, conversation: Conversation) -> None:
        """Copy conversation assignee/team onto a ticket after auto-assign."""
        ticket.assigned_user_id = conversation.assigned_user_id
        ticket.assigned_team_id = conversation.assigned_team_id or ticket.assigned_team_id
        await self.db.flush()

    async def sync_manual_assignment(
        self,
        organization_id: str,
        *,
        conversation_id: str,
        assigned_team_id: str | None,
        assigned_user_id: str | None,
        ticket: Ticket | None = None,
        sync_linked_tickets: bool = True,
    ) -> None:
        """Apply an explicit manual team/user assignment and sync conversation + tickets."""
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None or conv.organization_id != organization_id:
            return
        old_user = conv.assigned_user_id
        conv.assigned_team_id = assigned_team_id
        conv.assigned_user_id = assigned_user_id
        if old_user != assigned_user_id:
            await self._adjust_active_count(old_user, -1)
            await self._adjust_active_count(assigned_user_id, 1)
        await self.db.flush()
        await self._publish_assigned(conv, organization_id)
        await self._sync_tickets_with_conversation(
            conversation_id,
            team_id=assigned_team_id,
            assigned_user_id=assigned_user_id,
            primary_ticket=ticket,
            sync_linked_tickets=sync_linked_tickets,
        )

    async def find_available_agent(
        self,
        team_id: str,
        *,
        allow_offline: bool = False,
        allow_away: bool = False,
    ) -> str | None:
        """Next ONLINE (by default) member of this team only — A→B→C→A via last_assigned_user_id."""
        team = await self.db.get(Team, team_id)
        if team is None:
            return None
        members = await self.db.execute(select(TeamMember.user_id).where(TeamMember.team_id == team_id))
        user_ids = [row[0] for row in members.all()]
        if not user_ids:
            return None
        result = await self.db.execute(
            select(AgentAvailability).where(AgentAvailability.user_id.in_(user_ids))
        )
        agents = list(result.scalars().all())
        eligible = [a for a in agents if self._is_eligible(a, allow_offline, allow_away)]
        if not eligible:
            return None
        # Stable order so rotation is deterministic: A → B → C → A among eligible only.
        ordered_ids = sorted({a.user_id for a in eligible})
        last_id = team.last_assigned_user_id
        if last_id and last_id in ordered_ids:
            idx = ordered_ids.index(last_id)
            return ordered_ids[(idx + 1) % len(ordered_ids)]
        return ordered_ids[0]

    async def _user_on_team(self, user_id: str, team_id: str) -> bool:
        row = await self.db.scalar(
            select(TeamMember.id).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        return row is not None

    async def _sync_tickets_with_conversation(
        self,
        conversation_id: str,
        *,
        team_id: str | None,
        assigned_user_id: str | None,
        primary_ticket: Ticket | None,
        sync_linked_tickets: bool,
    ) -> None:
        tickets: list[Ticket] = []
        if primary_ticket is not None:
            tickets.append(primary_ticket)
        if sync_linked_tickets:
            result = await self.db.execute(select(Ticket).where(Ticket.conversation_id == conversation_id))
            for t in result.scalars().all():
                if primary_ticket is not None and t.id == primary_ticket.id:
                    continue
                tickets.append(t)
        for t in tickets:
            t.assigned_team_id = team_id
            t.assigned_user_id = assigned_user_id
        if tickets:
            await self.db.flush()

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
