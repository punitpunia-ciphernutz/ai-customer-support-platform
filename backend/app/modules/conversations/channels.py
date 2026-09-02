from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import ChannelType


@dataclass
class IncomingMessage:
    organization_id: str
    channel: ChannelType
    content: str
    customer_id: str | None = None
    customer_email: str | None = None
    customer_name: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class OutboundSendResult:
    external_message_id: str | None = None
    delivery_status: str | None = None


class ChannelAdapter(ABC):
    channel: ChannelType

    @abstractmethod
    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError

    @abstractmethod
    async def send(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> OutboundSendResult | None:
        raise NotImplementedError

    @abstractmethod
    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError

    @abstractmethod
    async def identify_customer(
        self, message: IncomingMessage, *, db: AsyncSession | None = None
    ) -> IncomingMessage:
        raise NotImplementedError


class WebChatAdapter(ChannelAdapter):
    channel = ChannelType.WEB_CHAT

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        return await self.normalize(raw)

    async def send(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> OutboundSendResult | None:
        _ = (conversation_id, content, metadata, db)
        return None

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        content = str(raw.get("content") or "").strip()
        return IncomingMessage(
            organization_id=str(raw["organization_id"]),
            channel=ChannelType.WEB_CHAT,
            content=content,
            customer_id=raw.get("customer_id"),
            customer_email=raw.get("customer_email"),
            customer_name=raw.get("customer_name"),
            external_id=raw.get("external_id"),
            metadata=dict(raw.get("metadata") or {}),
        )

    async def identify_customer(
        self, message: IncomingMessage, *, db: AsyncSession | None = None
    ) -> IncomingMessage:
        if db and message.customer_email and not message.customer_id:
            from app.modules.customers.resolver import CustomerResolver

            customer = await CustomerResolver(db).resolve_by_email(
                message.organization_id,
                message.customer_email,
                name=message.customer_name,
            )
            message.customer_id = customer.id
        return message


class EmailAdapter(ChannelAdapter):
    channel = ChannelType.EMAIL

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        return await self.normalize(raw)

    async def send(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> OutboundSendResult | None:
        if db is None:
            raise ValueError("EmailAdapter.send requires db session")
        from app.modules.conversations.email_delivery import EmailDeliveryService

        return await EmailDeliveryService(db).send_for_conversation(
            conversation_id,
            content,
            metadata or {},
        )

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        body = str(
            raw.get("body_text")
            or raw.get("content")
            or raw.get("text")
            or raw.get("body")
            or ""
        ).strip()
        meta = dict(raw.get("metadata") or {})
        for key in ("subject", "from_email", "to_email", "in_reply_to", "references", "headers"):
            if raw.get(key) is not None:
                meta[key] = raw[key]
        return IncomingMessage(
            organization_id=str(raw["organization_id"]),
            channel=ChannelType.EMAIL,
            content=body,
            customer_email=(raw.get("from_email") or raw.get("customer_email") or "").lower() or None,
            customer_name=raw.get("from_name") or raw.get("customer_name"),
            external_id=raw.get("external_message_id") or raw.get("message_id"),
            metadata=meta,
        )

    async def identify_customer(
        self, message: IncomingMessage, *, db: AsyncSession | None = None
    ) -> IncomingMessage:
        if db is None:
            raise ValueError("EmailAdapter.identify_customer requires db session")
        if not message.customer_email:
            raise ValueError("Email message missing sender address")
        from app.modules.customers.resolver import CustomerResolver

        customer = await CustomerResolver(db).resolve_by_email(
            message.organization_id,
            message.customer_email,
            name=message.customer_name,
        )
        message.customer_id = customer.id
        return message


class FormAdapter(ChannelAdapter):
    channel = ChannelType.FORM

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        return await self.normalize(raw)

    async def send(
        self,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> OutboundSendResult | None:
        _ = (conversation_id, content, metadata, db)
        return None

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        content = str(raw.get("content") or "").strip()
        return IncomingMessage(
            organization_id=str(raw["organization_id"]),
            channel=ChannelType.FORM,
            content=content,
            customer_id=raw.get("customer_id"),
            customer_email=raw.get("customer_email"),
            customer_name=raw.get("customer_name"),
            external_id=raw.get("external_id"),
            metadata=dict(raw.get("metadata") or {}),
        )

    async def identify_customer(
        self, message: IncomingMessage, *, db: AsyncSession | None = None
    ) -> IncomingMessage:
        if db and message.customer_email and not message.customer_id:
            from app.modules.customers.resolver import CustomerResolver

            customer = await CustomerResolver(db).resolve_by_email(
                message.organization_id,
                message.customer_email,
                name=message.customer_name,
            )
            message.customer_id = customer.id
        return message


ADAPTERS: dict[ChannelType, ChannelAdapter] = {
    ChannelType.WEB_CHAT: WebChatAdapter(),
    ChannelType.EMAIL: EmailAdapter(),
    ChannelType.FORM: FormAdapter(),
}


def get_adapter(channel: ChannelType) -> ChannelAdapter:
    return ADAPTERS[channel]
