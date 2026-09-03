"""Human escalation: ticket creation + AI handoff package."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Message, Priority, SenderType, Team, Ticket, TicketSource, TicketStatus
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.ai.domain.schemas import AIHandoffPackage, SupportAgentState
from app.modules.conversations.service import ConversationService
from app.modules.notifications.application.service import NotificationService


class EscalationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.conversations = ConversationService(db)

    def build_handoff_package(self, state: SupportAgentState, ai_run_id: str | None = None) -> AIHandoffPackage:
        customer = state.customer_context
        knowledge = [d.title for d in state.retrieved_documents]
        return AIHandoffPackage(
            customer_name=customer.name if customer else "Unknown",
            customer_company=customer.company if customer else None,
            issue_summary=state.escalation_summary or state.user_message,
            intent=state.intent.value if state.intent else "UNKNOWN",
            ai_confidence=state.support_confidence,
            confidence_breakdown=state.confidence_breakdown,
            knowledge_searched=knowledge,
            what_ai_tried=state.draft_response or "No response sent.",
            why_escalated=state.escalation_reason or "Escalation required",
            recommended_action="Human agent investigation.",
            sentiment=state.sentiment,
            language=state.language,
        )

    def render_handoff_note(self, package: AIHandoffPackage) -> str:
        lines = [
            "=== AI HANDOFF ===",
            f"Customer: {package.customer_name}" + (f" ({package.customer_company})" if package.customer_company else ""),
            f"Issue: {package.issue_summary}",
            f"Intent: {package.intent}",
            f"AI Confidence: {package.ai_confidence:.0%}",
            f"Knowledge searched: {', '.join(package.knowledge_searched) or 'None'}",
            f"What AI tried: {package.what_ai_tried}",
            f"Why escalated: {package.why_escalated}",
            f"Recommended action: {package.recommended_action}",
        ]
        if package.sentiment:
            lines.append(f"Sentiment: {package.sentiment}")
        return "\n".join(lines)

    async def create_from_ai_run(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
        ai_run_id: str,
        intent_team_map: dict[str, str] | None = None,
        notify_customer: bool = True,
    ) -> Ticket:
        return await self._create_ticket(
            state,
            organization_id=organization_id,
            source=TicketSource.AI_ESCALATION,
            ai_run_id=ai_run_id,
            intent_team_map=intent_team_map or {},
            notify_customer=notify_customer,
        )

    async def create_from_missed_chat(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
    ) -> Ticket:
        return await self._create_ticket(
            state,
            organization_id=organization_id,
            source=TicketSource.MISSED_CHAT,
            ai_run_id=None,
            intent_team_map={},
        )

    async def create_from_ai_timeout(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
        trigger_message_id: str,
    ) -> Ticket:
        ticket = await self._create_ticket(
            state,
            organization_id=organization_id,
            source=TicketSource.AUTOMATION,
            ai_run_id=None,
            intent_team_map={},
            notify_customer=False,
        )
        conversation = await self.conversations.get_conversation(organization_id, state.conversation_id or "")
        notice = Message(
            conversation_id=state.conversation_id,
            sender_type=SenderType.SYSTEM,
            sender_id=None,
            content=(
                "We weren't able to generate an automatic response in time. "
                "A support ticket has been created and our team will follow up with you shortly."
            ),
            metadata_={
                "internal": False,
                "timeout_escalation": True,
                "ticket_id": ticket.id,
                "trigger_message_id": trigger_message_id,
            },
        )
        self.db.add(notice)
        await self.db.flush()
        await self.conversations._publish_message(notice, conversation)  # noqa: SLF001
        return ticket

    async def _create_ticket(
        self,
        state: SupportAgentState,
        *,
        organization_id: str,
        source: TicketSource,
        ai_run_id: str | None,
        intent_team_map: dict[str, str],
        notify_customer: bool = True,
    ) -> Ticket:
        if not state.conversation_id:
            raise ValueError("conversation_id required for escalation")

        package = self.build_handoff_package(state, ai_run_id)
        priority = Priority.HIGH
        if state.sentiment and state.sentiment.upper() in {"ANGRY", "NEGATIVE", "FRUSTRATED"}:
            priority = Priority.HIGH
        if state.human_requested:
            priority = Priority.HIGH

        team_id = await self._resolve_team_id(organization_id, state, intent_team_map)
        conv = await self.conversations.get_conversation(organization_id, state.conversation_id)
        ticket = Ticket(
            organization_id=organization_id,
            conversation_id=state.conversation_id,
            customer_id=conv.customer_id,
            source=source,
            title=f"[{package.intent}] {state.user_message[:80]}",
            description=self.render_handoff_note(package),
            status=TicketStatus.OPEN,
            priority=priority,
            assigned_team_id=team_id,
        )
        self.db.add(ticket)
        await self.db.flush()
        await self.db.refresh(ticket)

        internal_note = self.render_handoff_note(package)
        from app.infrastructure.database.models import Message as MessageModel

        note = MessageModel(
            conversation_id=state.conversation_id,
            sender_type=SenderType.SYSTEM,
            sender_id=None,
            content=internal_note,
            metadata_={
                "internal": True,
                "ai_run_id": ai_run_id,
                "ai_escalation": True,
                "handoff_package": package.model_dump(mode="json"),
                "intent": state.intent.value if state.intent else None,
                "confidence": state.support_confidence,
                "ticket_id": ticket.id,
            },
        )
        self.db.add(note)
        await self.db.flush()

        conversation = await self.conversations.get_conversation(organization_id, state.conversation_id)
        await self.conversations._publish_message(note, conversation)  # noqa: SLF001

        if source == TicketSource.AI_ESCALATION and notify_customer:
            handoff = (
                "Thanks for your patience. I'm connecting you with a member of our support team "
                "who can help you further."
            )
            if (conversation.channel.value if hasattr(conversation.channel, "value") else str(conversation.channel)) == "EMAIL":
                await self.conversations.send_ai_reply(
                    state.conversation_id or "",
                    handoff,
                    {
                        "ai_run_id": ai_run_id,
                        "escalation": True,
                        "internal": False,
                    },
                )
            else:
                handoff_msg = Message(
                    conversation_id=state.conversation_id,
                    sender_type=SenderType.AI,
                    sender_id=None,
                    content=handoff,
                    channel=conversation.channel,
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
                payload={
                    "ticket_id": ticket.id,
                    "conversation_id": state.conversation_id,
                    "source": source.value,
                },
            )
        )
        return ticket

    async def _resolve_team_id(
        self, organization_id: str, state: SupportAgentState, intent_team_map: dict[str, str]
    ) -> str | None:
        """Assign AI escalation tickets from Settings intent → team map; else Support.

        Automations are unchanged and may still assign conversations independently.
        """
        mapped = ""
        if state.intent and intent_team_map:
            mapped = (intent_team_map.get(state.intent.value) or "").strip()
        notifier = NotificationService(self.db)
        team_id = await notifier.resolve_team_id(organization_id, mapped or "Support")
        if team_id is None and mapped:
            team_id = await notifier.resolve_team_id(organization_id, "Support")
        if team_id is not None:
            return team_id
        fallback = await self.db.execute(
            select(Team).where(Team.organization_id == organization_id).limit(1)
        )
        team = fallback.scalar_one_or_none()
        return team.id if team else None
