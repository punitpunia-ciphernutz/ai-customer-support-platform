from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    DeliveryStatus,
    Message,
    SenderType,
)
from app.infrastructure.email import get_email_provider
from app.infrastructure.email.base import SendEmailRequest
from app.modules.conversations.channels import OutboundSendResult
from app.modules.conversations.email_threading import EmailThreadingService


class EmailDeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def send_for_conversation(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> OutboundSendResult:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise ValueError("Conversation not found")
        customer: Customer = conversation.customer
        if not customer.email:
            raise ValueError("Customer has no email address")

        threading = EmailThreadingService(self.db)
        references = await threading.collect_thread_references(conversation_id)
        in_reply_to = references[-1] if references else None
        subject = metadata.get("subject") or threading.build_reply_subject(conversation.subject)

        provider_name = metadata.get("provider") or self.settings.email_provider
        provider = get_email_provider(provider_name)

        request = SendEmailRequest(
            to_email=customer.email,
            subject=subject,
            body_text=content,
            from_email=self.settings.email_from_address,
            in_reply_to=in_reply_to,
            references=references,
        )

        external_id = await provider.send(request)
        return OutboundSendResult(
            external_message_id=external_id,
            delivery_status=DeliveryStatus.SENT.value,
        )
