from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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


class ChannelAdapter(ABC):
    channel: ChannelType

    @abstractmethod
    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError

    @abstractmethod
    async def send(self, conversation_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError

    @abstractmethod
    async def identify_customer(self, message: IncomingMessage) -> IncomingMessage:
        raise NotImplementedError


class WebChatAdapter(ChannelAdapter):
    channel = ChannelType.WEB_CHAT

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        return await self.normalize(raw)

    async def send(self, conversation_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        # Delivery is via persisted Message + WebSocket fan-out.
        return None

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        return IncomingMessage(
            organization_id=str(raw["organization_id"]),
            channel=ChannelType.WEB_CHAT,
            content=str(raw["content"]),
            customer_id=raw.get("customer_id"),
            customer_email=raw.get("customer_email"),
            customer_name=raw.get("customer_name"),
            metadata=raw.get("metadata") or {},
        )

    async def identify_customer(self, message: IncomingMessage) -> IncomingMessage:
        return message


class EmailAdapter(ChannelAdapter):
    channel = ChannelType.EMAIL

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError("Email channel stub — not implemented on Day 1")

    async def send(self, conversation_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError("Email channel stub — not implemented on Day 1")

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError("Email channel stub — not implemented on Day 1")

    async def identify_customer(self, message: IncomingMessage) -> IncomingMessage:
        raise NotImplementedError("Email channel stub — not implemented on Day 1")


class FormAdapter(ChannelAdapter):
    channel = ChannelType.FORM

    async def receive(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError("Form channel stub — not implemented on Day 1")

    async def send(self, conversation_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        raise NotImplementedError("Form channel stub — not implemented on Day 1")

    async def normalize(self, raw: dict[str, Any]) -> IncomingMessage:
        raise NotImplementedError("Form channel stub — not implemented on Day 1")

    async def identify_customer(self, message: IncomingMessage) -> IncomingMessage:
        raise NotImplementedError("Form channel stub — not implemented on Day 1")


ADAPTERS: dict[ChannelType, ChannelAdapter] = {
    ChannelType.WEB_CHAT: WebChatAdapter(),
    ChannelType.EMAIL: EmailAdapter(),
    ChannelType.FORM: FormAdapter(),
}


def get_adapter(channel: ChannelType) -> ChannelAdapter:
    return ADAPTERS[channel]
