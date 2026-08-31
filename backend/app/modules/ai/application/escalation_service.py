"""Human escalation: ticket creation + internal AI note."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ActorType, Priority, SenderType, Team, Ticket, TicketStatus
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.ai.domain.schemas import SupportAgentState
from app.modules.conversations.service import ConversationService


class EscalationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conversations = ConversationService(db)

    async def create_from_ai_run(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
        ai_run_id: str,
        intent_team_map: dict[str, str] | None = None,
    ) -> Ticket:
        if not state.conversation_id:
            raise ValueError("conversation_id required for escalation")

        team_id = await self._resolve_team_id(organization_id, state, intent_team_map or {})
        ticket = Ticket(
            organization_id=organization_id,
            conversation_id=state.conversation_id,
            status=TicketStatus.OPEN,
            priority=Priority.HIGH if state.human_requested else Priority.NORMAL,
            assigned_team_id=team_id,
        )
        self.db.add(ticket)
        await self.db.flush()
        await self.db.refresh(ticket)

        knowledge_titles = ", ".join(d.title for d in state.retrieved_documents) or "None"
        internal_note = (
            "AI ESCALATION\n"
            f"Reason: {state.escalation_reason}\n"
            f"Intent: {state.intent}\n"
            f"Confidence: {state.support_confidence:.2f}\n"
            f"Summary: {state.escalation_summary or state.user_message}\n"
            f"Knowledge searched: {knowledge_titles}\n"
            f"Attempted response: {state.draft_response or 'None sent.'}\n"
            "Recommended: Human agent investigation."
        )

        from app.infrastructure.database.models import Message

        note = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.SYSTEM,
            sender_id=None,
            content=internal_note,
            metadata_={
                "internal": True,
                "ai_run_id": ai_run_id,
                "ai_escalation": True,
                "intent": state.intent.value if state.intent else None,
                "confidence": state.support_confidence,
                "ticket_id": ticket.id,
            },
        )
        self.db.add(note)
        await self.db.flush()

        conversation = await self.conversations.get_conversation(organization_id, state.conversation_id)
        await self.conversations._publish_message(note, conversation)  # noqa: SLF001

        handoff = (
            "Thanks for your patience. I'm connecting you with a member of our support team "
            "who can help you further."
        )
        handoff_msg = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=handoff,
            metadata_={
                "ai_run_id": ai_run_id,
                "escalation": True,
                "internal": False,
            },
        )
        self.db.add(handoff_msg)
        await self.db.flush()
        await self.conversations._publish_message(handoff_msg, conversation)  # noqa: SLF001

        await event_bus.publish(
            DomainEvent(
                name="ticket.created",
                organization_id=organization_id,
                payload={"ticket_id": ticket.id, "conversation_id": state.conversation_id, "source": "ai"},
            )
        )
        return ticket

    async def _resolve_team_id(
        self, organization_id: str, state: SupportAgentState, intent_team_map: dict[str, str]
    ) -> str | None:
        team_name = None
        if state.intent:
            team_name = intent_team_map.get(state.intent.value)
        if not team_name:
            team_name = "Support"
        result = await self.db.execute(
            select(Team).where(Team.organization_id == organization_id, Team.name == team_name)
        )
        team = result.scalar_one_or_none()
        if team is None:
            fallback = await self.db.execute(
                select(Team).where(Team.organization_id == organization_id, Team.name == "Support")
            )
            team = fallback.scalar_one_or_none()
        return team.id if team else None
