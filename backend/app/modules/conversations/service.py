"""Conversation application service — ChannelAdapter → persistence → events/audit."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import (
    ActorType,
    AIControlMode,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    Participant,
    SenderType,
    TeamMember,
    User,
)
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.ai.tasks_bridge import enqueue_ai_message_processing
from app.modules.auth.permissions import CONVERSATIONS_ASSIGN
from app.modules.conversations.channels import IncomingMessage, get_adapter
from app.modules.conversations.schemas import ConversationCreate, ConversationUpdate, MessageCreate


class ConversationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_conversations(self, user: User, view: str = "all") -> list[Conversation]:
        stmt = select(Conversation).where(Conversation.organization_id == user.organization_id)
        if view == "mine":
            stmt = stmt.where(Conversation.assigned_user_id == user.id)
        elif view == "unassigned":
            stmt = stmt.where(Conversation.assigned_user_id.is_(None))
        elif view == "team":
            team_ids = (
                await self.db.execute(select(TeamMember.team_id).where(TeamMember.user_id == user.id))
            ).scalars().all()
            stmt = stmt.where(Conversation.assigned_team_id.in_(list(team_ids) or ["__none__"]))
        stmt = stmt.order_by(Conversation.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_conversation(self, organization_id: str, conversation_id: str) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    async def get_conversation_by_id(self, conversation_id: str) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    async def create_conversation(self, user: User, body: ConversationCreate) -> Conversation:
        customer = await self._get_customer(user.organization_id, body.customer_id)
        adapter = get_adapter(body.channel)
        incoming = await adapter.normalize(
            {
                "organization_id": user.organization_id,
                "content": body.initial_message or "",
                "customer_id": customer.id,
                "customer_email": customer.email,
                "customer_name": customer.name,
                "metadata": {},
            }
        )
        incoming = await adapter.identify_customer(incoming)
        return await self._create_from_incoming(
            incoming,
            channel=body.channel,
            priority=body.priority,
            subject=body.subject,
            initial_message=body.initial_message,
        )

    async def create_public_conversation(self, body: ConversationCreate) -> Conversation:
        customer = await self.db.execute(select(Customer).where(Customer.id == body.customer_id))
        cust = customer.scalar_one_or_none()
        if cust is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        adapter = get_adapter(body.channel)
        incoming = await adapter.normalize(
            {
                "organization_id": cust.organization_id,
                "content": body.initial_message or "",
                "customer_id": cust.id,
                "customer_email": cust.email,
                "customer_name": cust.name,
                "metadata": {},
            }
        )
        incoming = await adapter.identify_customer(incoming)
        return await self._create_from_incoming(
            incoming,
            channel=body.channel,
            priority=body.priority,
            subject=body.subject,
            initial_message=body.initial_message,
        )

    async def update_conversation(
        self, user: User, conversation_id: str, body: ConversationUpdate
    ) -> Conversation:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        old = {
            "status": conversation.status.value,
            "priority": conversation.priority.value,
            "assigned_user_id": conversation.assigned_user_id,
            "assigned_team_id": conversation.assigned_team_id,
        }
        data = body.model_dump(exclude_unset=True)

        if "assigned_user_id" in data or "assigned_team_id" in data:
            perms = set(user.role.permissions or [])
            if CONVERSATIONS_ASSIGN not in perms:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Missing assign permission"
                )

        for key, value in data.items():
            setattr(conversation, key, value)
        await self.db.flush()
        await self.db.refresh(conversation)

        new = {
            "status": conversation.status.value,
            "priority": conversation.priority.value,
            "assigned_user_id": conversation.assigned_user_id,
            "assigned_team_id": conversation.assigned_team_id,
        }

        event_name = "conversation.updated"
        if old["assigned_user_id"] != new["assigned_user_id"] or old["assigned_team_id"] != new[
            "assigned_team_id"
        ]:
            event_name = "conversation.assigned"
            await write_audit(
                self.db,
                organization_id=user.organization_id,
                actor_type=ActorType.USER,
                actor_id=user.id,
                action="conversation.assigned",
                entity_type="conversation",
                entity_id=conversation.id,
                old_value=old,
                new_value=new,
            )
        if old["status"] != ConversationStatus.CLOSED.value and new["status"] == ConversationStatus.CLOSED.value:
            event_name = "conversation.closed"
            await write_audit(
                self.db,
                organization_id=user.organization_id,
                actor_type=ActorType.USER,
                actor_id=user.id,
                action="conversation.closed",
                entity_type="conversation",
                entity_id=conversation.id,
                old_value=old,
                new_value=new,
            )

        await event_bus.publish(
            DomainEvent(
                name=event_name,
                organization_id=user.organization_id,
                payload={"conversation_id": conversation.id, **new},
            )
        )
        return conversation

    async def list_messages(self, organization_id: str, conversation_id: str) -> list[Message]:
        await self.get_conversation(organization_id, conversation_id)
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def add_agent_message(
        self, user: User, conversation_id: str, body: MessageCreate
    ) -> Message:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        adapter = get_adapter(conversation.channel)
        sender_id = user.id if body.sender_type == SenderType.AGENT else body.metadata.get("sender_id")
        incoming = await adapter.normalize(
            {
                "organization_id": user.organization_id,
                "content": body.content,
                "customer_id": conversation.customer_id,
                "metadata": {**(body.metadata or {}), "sender_type": body.sender_type.value},
            }
        )
        await adapter.send(conversation.id, incoming.content, incoming.metadata)

        msg = Message(
            conversation_id=conversation.id,
            sender_type=body.sender_type,
            sender_id=sender_id,
            content=incoming.content,
            metadata_=incoming.metadata or {},
        )
        self.db.add(msg)
        if conversation.status == ConversationStatus.CLOSED:
            conversation.status = ConversationStatus.OPEN
        await self.db.flush()
        await self.db.refresh(msg)
        await self._publish_message(msg, conversation)
        await event_bus.publish(
            DomainEvent(
                name="conversation.updated",
                organization_id=user.organization_id,
                payload={"conversation_id": conversation.id},
            )
        )
        return msg

    async def add_public_message(
        self, conversation_id: str, customer_id: str, content: str, metadata: dict[str, Any] | None = None
    ) -> Message:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None or conversation.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Conversation not found")

        adapter = get_adapter(conversation.channel)
        incoming = await adapter.receive(
            {
                "organization_id": conversation.organization_id,
                "content": content,
                "customer_id": customer_id,
                "metadata": metadata or {},
            }
        )
        incoming = await adapter.identify_customer(incoming)

        msg = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer_id,
            content=incoming.content,
            metadata_=incoming.metadata or {},
        )
        self.db.add(msg)
        if conversation.status == ConversationStatus.CLOSED:
            conversation.status = ConversationStatus.OPEN
        await self.db.flush()
        await self.db.refresh(msg)
        await self._publish_message(msg, conversation)
        return msg

    async def list_public_messages(self, conversation_id: str, customer_id: str) -> list[Message]:
        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        conversation = result.scalar_one_or_none()
        if conversation is None or conversation.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        msgs = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return [
            m
            for m in msgs.scalars().all()
            if not (m.metadata_ or {}).get("internal")
        ]

    async def _create_from_incoming(
        self,
        incoming: IncomingMessage,
        *,
        channel: Any,
        priority: Any,
        subject: str | None,
        initial_message: str | None,
    ) -> Conversation:
        customer_id = incoming.customer_id
        if not customer_id:
            raise HTTPException(status_code=400, detail="Customer could not be identified")

        conversation = Conversation(
            organization_id=incoming.organization_id,
            customer_id=customer_id,
            channel=channel,
            status=ConversationStatus.OPEN,
            priority=priority,
            subject=subject,
        )
        self.db.add(conversation)
        await self.db.flush()
        self.db.add(
            Participant(
                conversation_id=conversation.id,
                participant_type=SenderType.CUSTOMER,
                participant_id=customer_id,
            )
        )
        if initial_message:
            msg = Message(
                conversation_id=conversation.id,
                sender_type=SenderType.CUSTOMER,
                sender_id=customer_id,
                content=initial_message,
                metadata_=incoming.metadata or {},
            )
            self.db.add(msg)
            await self.db.flush()
            await self._publish_message(msg, conversation)
        await self.db.refresh(conversation)
        await event_bus.publish(
            DomainEvent(
                name="conversation.created",
                organization_id=incoming.organization_id,
                payload={"conversation_id": conversation.id, "customer_id": customer_id},
            )
        )
        return conversation

    async def takeover(self, user: User, conversation_id: str) -> Conversation:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        conversation.ai_control_mode = AIControlMode.HUMAN_CONTROL
        await write_audit(
            self.db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="conversation.takeover",
            entity_type="conversation",
            entity_id=conversation_id,
            new_value={"ai_control_mode": AIControlMode.HUMAN_CONTROL.value},
        )
        await self.db.flush()
        await self.db.refresh(conversation)
        return conversation

    async def return_to_ai(self, user: User, conversation_id: str) -> Conversation:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        conversation.ai_control_mode = AIControlMode.AI_CONTROL
        await write_audit(
            self.db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="conversation.return_to_ai",
            entity_type="conversation",
            entity_id=conversation_id,
            new_value={"ai_control_mode": AIControlMode.AI_CONTROL.value},
        )
        await self.db.flush()
        await self.db.refresh(conversation)
        return conversation

    async def create_ticket_from_conversation(self, user: User, conversation_id: str):
        from app.infrastructure.database.models import TicketSource
        from app.modules.ai.application.escalation_service import EscalationService
        from app.modules.ai.domain.schemas import SupportAgentState

        conversation = await self.get_conversation(user.organization_id, conversation_id)
        state = SupportAgentState(
            conversation_id=conversation.id,
            organization_id=conversation.organization_id,
            user_message="Agent-created ticket",
            escalation_reason="Created by agent",
        )
        return await EscalationService(self.db)._create_ticket(  # noqa: SLF001
            state,
            organization_id=user.organization_id,
            source=TicketSource.AGENT_CREATED,
            ai_run_id=None,
            intent_team_map={},
        )

    async def update_suggestion_status(
        self,
        user: User,
        conversation_id: str,
        suggestion_message_id: str,
        status: str,
        *,
        event: str,
    ) -> Message:
        await self.get_conversation(user.organization_id, conversation_id)
        msg = await self.db.get(Message, suggestion_message_id)
        if msg is None or msg.conversation_id != conversation_id:
            raise ValueError("Suggestion message not found")
        if not msg.metadata_ or not msg.metadata_.get("suggestion"):
            raise ValueError("Message is not an AI suggestion")
        meta = dict(msg.metadata_)
        meta["suggestion_status"] = status
        meta["event"] = event
        msg.metadata_ = meta
        await self.db.flush()
        await self.db.refresh(msg)
        return msg

    async def regenerate_suggestion(self, user: User, conversation_id: str, suggestion_message_id: str) -> Message:
        from app.modules.ai.application.ai_service import AIService

        conversation = await self.get_conversation(user.organization_id, conversation_id)
        msg = await self.db.get(Message, suggestion_message_id)
        if msg is None or msg.conversation_id != conversation_id:
            raise ValueError("Suggestion message not found")
        trigger_id = (msg.metadata_ or {}).get("trigger_message_id")
        if not trigger_id:
            raise ValueError("Suggestion missing trigger message")
        await self.update_suggestion_status(
            user,
            conversation_id,
            suggestion_message_id,
            "rejected",
            event="suggestion.rejected",
        )
        await AIService(self.db).run_support_agent(
            conversation_id,
            trigger_id,
            persist_side_effects=True,
            force=True,
        )
        result = await self.db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.metadata_["suggestion"].astext == "true",
                Message.metadata_["suggestion_status"].astext == "generated",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        new_suggestion = result.scalar_one_or_none()
        if new_suggestion is None:
            raise ValueError("Failed to regenerate suggestion")
        return new_suggestion

    async def _get_customer(self, org_id: str, customer_id: str) -> Customer:
        result = await self.db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
        )
        customer = result.scalar_one_or_none()
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    async def _publish_message(self, msg: Message, conversation: Conversation) -> None:
        await event_bus.publish(
            DomainEvent(
                name="message.created",
                organization_id=conversation.organization_id,
                payload={
                    "message_id": msg.id,
                    "conversation_id": conversation.id,
                    "sender_type": msg.sender_type.value,
                    "sender_id": msg.sender_id,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                },
            )
        )
        enqueue_ai_message_processing(msg.id, msg.sender_type.value)
