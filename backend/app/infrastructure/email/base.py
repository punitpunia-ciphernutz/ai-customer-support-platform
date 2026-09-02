from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedEmail:
    external_message_id: str
    from_email: str
    from_name: str | None
    to_email: str
    subject: str
    body_text: str
    body_html: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    raw_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SendEmailRequest:
    to_email: str
    subject: str
    body_text: str
    from_email: str | None = None
    reply_to: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)


class EmailProvider(ABC):
    name: str

    @abstractmethod
    def verify(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify webhook signature."""

    @abstractmethod
    def parse(self, payload: dict[str, Any]) -> ParsedEmail:
        """Parse provider webhook payload into normalized email."""

    @abstractmethod
    async def send(self, request: SendEmailRequest) -> str:
        """Send email and return external message id."""

    def normalize(self, parsed: ParsedEmail) -> dict[str, Any]:
        return {
            "external_message_id": parsed.external_message_id,
            "from_email": parsed.from_email,
            "from_name": parsed.from_name,
            "to_email": parsed.to_email,
            "subject": parsed.subject,
            "body_text": parsed.body_text,
            "body_html": parsed.body_html,
            "in_reply_to": parsed.in_reply_to,
            "references": parsed.references,
            "attachments": parsed.attachments,
            "headers": parsed.raw_headers,
        }
