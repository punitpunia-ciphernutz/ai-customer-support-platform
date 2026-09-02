from __future__ import annotations

import re
from typing import Any

from app.infrastructure.database.models import ChannelType, SenderType
from app.modules.conversations.channels import IncomingMessage


def normalize_subject(subject: str) -> str:
    cleaned = re.sub(r"^(re|fwd|fw):\s*", "", subject.strip(), flags=re.IGNORECASE)
    while True:
        next_val = re.sub(r"^(re|fwd|fw):\s*", "", cleaned, flags=re.IGNORECASE)
        if next_val == cleaned:
            break
        cleaned = next_val
    return cleaned.strip().lower()


class MessageNormalizer:
    @staticmethod
    def from_incoming(incoming: IncomingMessage, *, sender_type: SenderType) -> dict[str, Any]:
        return {
            "channel": incoming.channel.value,
            "sender_type": sender_type.value,
            "content": incoming.content,
            "external_message_id": incoming.external_id,
            "metadata": dict(incoming.metadata or {}),
        }

    @staticmethod
    def from_raw(
        *,
        channel: ChannelType,
        sender_type: SenderType,
        content: str,
        external_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "channel": channel.value,
            "sender_type": sender_type.value,
            "content": content,
            "external_message_id": external_message_id,
            "metadata": dict(metadata or {}),
        }
