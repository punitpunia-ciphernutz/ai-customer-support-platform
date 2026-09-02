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
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    DeliveryStatus,
    Message,
    Participant,
    SenderType,
    TeamMember,
    User,
)
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.ai.tasks_bridge import enqueue_ai_message_processing
from app.modules.auth.permissions import CONVERSATIONS_ASSIGN
from app.modules.assignment.application.service import AssignmentService
from app.modules.channels.idempotency import IdempotencyService
from app.modules.conversations.channels import IncomingMessage, get_adapter
from app.modules.conversations.email_threading import EmailThreadingService
from app.modules.conversations.events import message_delivered, message_failed, message_received, message_sent
from app.modules.conversations.normalizer import normalize_subject
from app.modules.conversations.schemas import ConversationCreate, ConversationUpdate, MessageCreate
from app.modules.channels.schemas import EmailSendRequest
from app.modules.sla.application.service import SLAService


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
        elif view == "web_chat":
            stmt = stmt.where(Conversation.channel == ChannelType.WEB_CHAT)
        elif view == "email":
            stmt = stmt.where(Conversation.channel == ChannelType.EMAIL)
        elif view == "form":
            stmt = stmt.where(Conversation.channel == ChannelType.FORM)
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
        incoming = await adapter.identify_customer(incoming, db=self.db)
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
        incoming = await adapter.identify_customer(incoming, db=self.db)
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

        assignment = AssignmentService(self.db)
        if old["assigned_user_id"] != conversation.assigned_user_id:
            await assignment._adjust_active_count(old["assigned_user_id"], -1)  # noqa: SLF001
            await assignment._adjust_active_count(conversation.assigned_user_id, 1)  # noqa: SLF001

        sla = SLAService(self.db)
        if old["priority"] != conversation.priority.value:
            await sla.start_timers_for_conversation(
                user.organization_id, conversation.id, conversation.priority
            )
        if old["status"] != ConversationStatus.CLOSED.value and conversation.status == ConversationStatus.CLOSED:
            await sla.complete_resolution(conversation.id)
            await assignment._adjust_active_count(conversation.assigned_user_id, -1)  # noqa: SLF001
        elif old["status"] == ConversationStatus.CLOSED.value and conversation.status != ConversationStatus.CLOSED:
            await sla.resume_timers(conversation.id)
            if conversation.assigned_user_id:
                await assignment._adjust_active_count(conversation.assigned_user_id, 1)  # noqa: SLF001

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
        if old["status"] == ConversationStatus.CLOSED.value and new["status"] != ConversationStatus.CLOSED.value:
            event_name = "conversation.reopened"
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

    async def enrich_message(self, message: Message) -> dict[str, Any]:
        from app.modules.attachments.service import AttachmentService
        from app.modules.channels.schemas import AttachmentOut

        attachment_service = AttachmentService(self.db)
        grouped = await attachment_service.list_for_messages([message.id])
        payload = {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "sender_type": message.sender_type,
            "sender_id": message.sender_id,
            "content": message.content,
            "channel": message.channel,
            "external_message_id": message.external_message_id,
            "delivery_status": message.delivery_status.value if message.delivery_status else None,
            "metadata_": message.metadata_ or {},
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "attachments": [],
        }
        for attachment in grouped.get(message.id, []):
            att_out = AttachmentOut.model_validate(attachment)
            att_out.download_url = await attachment_service.get_download_url(attachment)
            payload["attachments"].append(att_out)
        return payload

    async def list_messages_enriched(self, organization_id: str, conversation_id: str) -> list[dict[str, Any]]:
        messages = await self.list_messages(organization_id, conversation_id)
        return [await self.enrich_message(message) for message in messages]

    async def add_agent_message(
        self, user: User, conversation_id: str, body: MessageCreate
    ) -> Message:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        message = await self._create_outbound_message(
            conversation=conversation,
            organization_id=user.organization_id,
            sender_type=body.sender_type,
            sender_id=user.id if body.sender_type == SenderType.AGENT else body.metadata.get("sender_id"),
            content=body.content,
            metadata=body.metadata,
        )
        if body.sender_type == SenderType.AGENT:
            await SLAService(self.db).complete_first_response(conversation_id)
        return message

    async def send_email_reply(
        self, user: User, conversation_id: str, body: EmailSendRequest
    ) -> Message:
        conversation = await self.get_conversation(user.organization_id, conversation_id)
        if conversation.channel != ChannelType.EMAIL:
            raise HTTPException(status_code=400, detail="Conversation is not an email channel")
        meta = dict(body.metadata or {})
        if body.subject:
            meta["subject"] = body.subject
        if body.attachment_ids:
            meta["attachment_ids"] = body.attachment_ids
        return await self._create_outbound_message(
            conversation=conversation,
            organization_id=user.organization_id,
            sender_type=SenderType.AGENT,
            sender_id=user.id,
            content=body.content,
            metadata=meta,
        )

    async def receive_inbound_email(
        self,
        organization_id: str,
        provider: str,
        normalized: dict[str, Any],
    ) -> tuple[Conversation, Message, bool]:
        external_id = normalized.get("external_message_id")
        if not external_id:
            raise HTTPException(status_code=400, detail="external_message_id required")

        idempotency = IdempotencyService(self.db)
        if await idempotency.is_processed(organization_id, provider, external_id):
            result = await self.db.execute(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.organization_id == organization_id,
                    Message.external_message_id == external_id,
                )
                .limit(1)
            )
            msg = result.scalar_one_or_none()
            if msg is not None:
                conv = await self.get_conversation_by_id(msg.conversation_id)
                return conv, msg, False
            raise HTTPException(status_code=409, detail="Duplicate webhook without message record")

        normalized["organization_id"] = organization_id

        from app.infrastructure.database.models import ChannelType as CT
        from app.modules.channels.service import ChannelService

        channel_cfg = await ChannelService(self.db).get_channel(organization_id, CT.EMAIL)
        if not channel_cfg.enabled:
            raise HTTPException(status_code=403, detail="Email channel is disabled")

        adapter = get_adapter(ChannelType.EMAIL)
        incoming = await adapter.normalize(normalized)
        incoming = await adapter.identify_customer(incoming, db=self.db)
        return await self.receive_inbound(incoming, provider=provider, created=True)

    async def receive_inbound(
        self,
        incoming: IncomingMessage,
        *,
        provider: str | None = None,
        created: bool = True,
    ) -> tuple[Conversation, Message, bool]:
        adapter = get_adapter(incoming.channel)
        if not incoming.customer_id:
            incoming = await adapter.identify_customer(incoming, db=self.db)

        conversation: Conversation | None = None
        subject = (incoming.metadata or {}).get("subject")

        if incoming.channel == ChannelType.EMAIL:
            threading = EmailThreadingService(self.db)
            conversation = await threading.find_conversation(
                incoming.organization_id,
                in_reply_to=(incoming.metadata or {}).get("in_reply_to"),
                references=list((incoming.metadata or {}).get("references") or []),
                customer_id=incoming.customer_id or "",
                subject=subject or "(no subject)",
            )

        if conversation is None:
            thread_id = normalize_subject(subject) if subject else None
            conversation = Conversation(
                organization_id=incoming.organization_id,
                customer_id=incoming.customer_id,
                channel=incoming.channel,
                status=ConversationStatus.OPEN,
                subject=subject,
                thread_id=thread_id,
            )
            self.db.add(conversation)
            await self.db.flush()
            self.db.add(
                Participant(
                    conversation_id=conversation.id,
                    participant_type=SenderType.CUSTOMER,
                    participant_id=incoming.customer_id,
                )
            )
            await event_bus.publish(
                DomainEvent(
                    name="conversation.created",
                    organization_id=incoming.organization_id,
                    payload={
                        "conversation_id": conversation.id,
                        "customer_id": incoming.customer_id,
                        "channel": incoming.channel.value,
                    },
                )
            )
            await SLAService(self.db).start_timers_for_conversation(
                incoming.organization_id,
                conversation.id,
                conversation.priority,
            )
            from app.modules.ai.application.missed_chat_service import MissedChatService

            await MissedChatService(self.db).schedule_check_if_needed(conversation.id, incoming.organization_id)
        elif subject and not conversation.subject:
            conversation.subject = subject

        msg = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=incoming.customer_id,
            content=incoming.content,
            channel=incoming.channel,
            external_message_id=incoming.external_id,
            metadata_=incoming.metadata or {},
        )
        self.db.add(msg)
        await self.db.flush()
        await self.db.refresh(msg)

        attachment_items = (incoming.metadata or {}).get("attachments") or []
        if attachment_items:
            from app.modules.attachments.service import AttachmentService

            await AttachmentService(self.db).store_inbound(
                organization_id=incoming.organization_id,
                message_id=msg.id,
                items=attachment_items,
            )

        if provider and incoming.external_id:
            await IdempotencyService(self.db).record(
                incoming.organization_id,
                provider,
                incoming.external_id,
                msg.id,
            )

        await self._publish_message(msg, conversation)
        await self._publish_channel_event(
            message_received(
                channel=incoming.channel,
                provider=provider,
                external_message_id=incoming.external_id,
                conversation_id=conversation.id,
                message_id=msg.id,
                metadata={"subject": subject},
            ),
            incoming.organization_id,
        )
        return conversation, msg, created

    async def _create_outbound_message(
        self,
        *,
        conversation: Conversation,
        organization_id: str,
        sender_type: SenderType,
        sender_id: str | None,
        content: str,
        metadata: dict[str, Any] | None,
    ) -> Message:
        adapter = get_adapter(conversation.channel)
        meta = dict(metadata or {})
        meta.setdefault("sender_type", sender_type.value)

        msg = Message(
            conversation_id=conversation.id,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content,
            channel=conversation.channel,
            delivery_status=DeliveryStatus.QUEUED if conversation.channel == ChannelType.EMAIL else None,
            metadata_=meta,
        )
        self.db.add(msg)
        was_closed = conversation.status == ConversationStatus.CLOSED
        if was_closed:
            conversation.status = ConversationStatus.OPEN
        await self.db.flush()

        if was_closed:
            await SLAService(self.db).resume_timers(conversation.id)
            await event_bus.publish(
                DomainEvent(
                    name="conversation.reopened",
                    organization_id=organization_id,
                    payload={"conversation_id": conversation.id},
                )
            )

        attachment_ids = list(meta.pop("attachment_ids", []) or [])
        if attachment_ids:
            from app.modules.attachments.service import AttachmentService

            attachment_service = AttachmentService(self.db)
            for attachment_id in attachment_ids:
                await attachment_service.link_to_message(attachment_id, msg.id)
            meta["attachment_ids"] = attachment_ids

        if conversation.channel == ChannelType.EMAIL and sender_type in {SenderType.AGENT, SenderType.AI}:
            msg.delivery_status = DeliveryStatus.SENDING
            await self.db.flush()
            try:
                result = await adapter.send(
                    conversation.id,
                    content,
                    meta,
                    db=self.db,
                )
                if result and result.external_message_id:
                    msg.external_message_id = result.external_message_id
                msg.delivery_status = DeliveryStatus.SENT
            except Exception as exc:
                msg.delivery_status = DeliveryStatus.FAILED
                msg.metadata_ = {**msg.metadata_, "delivery_error": str(exc)}
                await self._publish_channel_event(
                    message_failed(
                        channel=conversation.channel,
                        provider=None,
                        external_message_id=msg.external_message_id,
                        conversation_id=conversation.id,
                        message_id=msg.id,
                        metadata={"error": str(exc)},
                    ),
                    organization_id,
                )
        else:
            await adapter.send(conversation.id, content, meta, db=self.db)

        await self.db.flush()
        await self.db.refresh(msg)
        await self._publish_message(msg, conversation)
        if conversation.channel == ChannelType.EMAIL and msg.delivery_status == DeliveryStatus.SENT:
            await self._publish_channel_event(
                message_sent(
                    channel=conversation.channel,
                    provider=None,
                    external_message_id=msg.external_message_id,
                    conversation_id=conversation.id,
                    message_id=msg.id,
                ),
                organization_id,
            )
            await self._publish_channel_event(
                message_delivered(
                    channel=conversation.channel,
                    provider=None,
                    external_message_id=msg.external_message_id,
                    conversation_id=conversation.id,
                    message_id=msg.id,
                    metadata={"simulated": True},
                ),
                organization_id,
            )
        await event_bus.publish(
            DomainEvent(
                name="conversation.updated",
                organization_id=organization_id,
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
        incoming = await adapter.identify_customer(incoming, db=self.db)

        msg = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer_id,
            content=incoming.content,
            channel=conversation.channel,
            metadata_=incoming.metadata or {},
        )
        self.db.add(msg)
        was_closed = conversation.status == ConversationStatus.CLOSED
        if was_closed:
            conversation.status = ConversationStatus.OPEN
        await self.db.flush()
        if was_closed:
            await SLAService(self.db).resume_timers(conversation.id)
            await event_bus.publish(
                DomainEvent(
                    name="conversation.reopened",
                    organization_id=conversation.organization_id,
                    payload={"conversation_id": conversation.id},
                )
            )
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
                channel=channel,
                metadata_=incoming.metadata or {},
            )
            self.db.add(msg)
            await self.db.flush()
            await self._publish_message(msg, conversation)
        await self.db.refresh(conversation)
        await SLAService(self.db).start_timers_for_conversation(
            incoming.organization_id,
            conversation.id,
            conversation.priority,
        )
        from app.modules.ai.application.missed_chat_service import MissedChatService

        await MissedChatService(self.db).schedule_check_if_needed(conversation.id, incoming.organization_id)
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

    async def send_ai_reply(self, conversation_id: str, content: str, metadata: dict[str, Any]) -> Message:
        """Send AI-generated reply through channel adapter (email delivery when applicable)."""
        conversation = await self.get_conversation_by_id(conversation_id)
        return await self._create_outbound_message(
            conversation=conversation,
            organization_id=conversation.organization_id,
            sender_type=SenderType.AI,
            sender_id=None,
            content=content,
            metadata=metadata,
        )

    async def _publish_channel_event(self, event, organization_id: str) -> None:
        await event_bus.publish(
            DomainEvent(
                name=event.name,
                organization_id=organization_id,
                payload={
                    "channel": event.channel.value,
                    "provider": event.provider,
                    "external_message_id": event.external_message_id,
                    "conversation_id": event.conversation_id,
                    "message_id": event.message_id,
                    "metadata": event.metadata,
                },
            )
        )

    async def _publish_message(self, msg: Message, conversation: Conversation) -> None:
        channel = msg.channel or conversation.channel
        channel_value = channel.value if hasattr(channel, "value") else str(channel)
        delivery_value = (
            msg.delivery_status.value if msg.delivery_status and hasattr(msg.delivery_status, "value") else msg.delivery_status
        )
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
                    "channel": channel_value,
                    "delivery_status": delivery_value,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                },
            )
        )
        enqueue_ai_message_processing(msg.id, msg.sender_type.value)
