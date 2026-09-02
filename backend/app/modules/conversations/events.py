from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.database.models import ChannelType


@dataclass
class ChannelEvent:
    name: str
    channel: ChannelType
    provider: str | None
    external_message_id: str | None
    conversation_id: str | None
    message_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def message_received(**kwargs: Any) -> ChannelEvent:
    return ChannelEvent(name="message.received", **kwargs)


def message_sent(**kwargs: Any) -> ChannelEvent:
    return ChannelEvent(name="message.sent", **kwargs)


def message_delivered(**kwargs: Any) -> ChannelEvent:
    return ChannelEvent(name="message.delivered", **kwargs)


def message_failed(**kwargs: Any) -> ChannelEvent:
    return ChannelEvent(name="message.failed", **kwargs)
