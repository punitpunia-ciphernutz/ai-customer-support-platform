"""Template email auto-responder for new inbound email threads."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    ChannelType,
    Conversation,
    Customer,
    Message,
    SenderType,
)
from app.modules.channels.service import ChannelService

logger = logging.getLogger(__name__)

SETTINGS_ENABLED = "email_auto_reply_enabled"
SETTINGS_SUBJECT = "email_auto_reply_subject"
SETTINGS_BODY = "email_auto_reply_body"

DEFAULT_SUBJECT = "We received your message"
DEFAULT_BODY = (
    "Hi {{customer_name}},\n\n"
    "Thanks for contacting us. We've received your email and will get back to you soon.\n\n"
    "— Support"
)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def is_auto_submitted_or_bounce(headers: dict[str, Any] | None) -> bool:
    """Return True when inbound headers look like an auto-reply, bounce, or list mail."""
    if not headers:
        return False
    normalized = {str(k).lower(): str(v).strip().lower() for k, v in headers.items()}

    auto_submitted = normalized.get("auto-submitted", "")
    if auto_submitted and auto_submitted != "no":
        return True

    suppress = normalized.get("x-auto-response-suppress", "")
    if suppress and suppress not in {"none", "no"}:
        return True

    precedence = normalized.get("precedence", "")
    if precedence in {"bulk", "junk", "list", "auto_reply", "autoreply"}:
        return True

    for key in ("x-autoreply", "x-autorespond", "x-loop"):
        if normalized.get(key) in {"yes", "true", "1"}:
            return True

    # Common bounce / mailer-daemon senders are handled by caller via from_email when needed.
    return False


def looks_like_mailer_daemon(from_email: str | None) -> bool:
    if not from_email:
        return False
    local = from_email.lower().split("@", 1)[0]
    return local in {"mailer-daemon", "mailerdaemon", "postmaster"}


def render_template(template: str, values: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    return _PLACEHOLDER_RE.sub(_replace, template)


class EmailAutoResponderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def maybe_send_for_inbound(
        self,
        *,
        conversation: Conversation,
        inbound_message: Message,
        inbound_metadata: dict[str, Any] | None = None,
    ) -> Message | None:
        """Send a configured auto-reply when this is the first message of an email thread."""
        if conversation.channel != ChannelType.EMAIL:
            return None

        meta = dict(inbound_metadata or inbound_message.metadata_ or {})
        headers = meta.get("headers") if isinstance(meta.get("headers"), dict) else {}
        from_email = (meta.get("from_email") or "").strip().lower() or None

        if is_auto_submitted_or_bounce(headers) or looks_like_mailer_daemon(from_email):
            logger.info(
                "Skipping email auto-reply for conversation %s (auto-submitted/bounce)",
                conversation.id,
            )
            return None

        if not await self._is_first_customer_message(conversation.id, inbound_message.id):
            return None

        if await self._already_sent(conversation.id):
            return None

        cfg = await ChannelService(self.db).get_channel(conversation.organization_id, ChannelType.EMAIL)
        settings = dict(cfg.settings or {})
        if not bool(settings.get(SETTINGS_ENABLED)):
            return None

        subject_tpl = str(settings.get(SETTINGS_SUBJECT) or "").strip() or DEFAULT_SUBJECT
        body_tpl = str(settings.get(SETTINGS_BODY) or "").strip() or DEFAULT_BODY

        customer = await self.db.get(Customer, conversation.customer_id)
        values = {
            "customer_name": (customer.name if customer and customer.name else None)
            or (customer.email if customer else None)
            or "there",
            "customer_email": (customer.email if customer else "") or "",
            "subject": conversation.subject or meta.get("subject") or "",
            "conversation_id": conversation.id,
            "ticket_id": "",
        }
        subject = render_template(subject_tpl, values)
        body = render_template(body_tpl, values)

        from app.modules.conversations.service import ConversationService

        try:
            return await ConversationService(self.db).send_auto_responder_reply(
                conversation_id=conversation.id,
                content=body,
                subject=subject,
                metadata={
                    "auto_responder": True,
                    "trigger_message_id": inbound_message.id,
                    "subject": subject,
                },
            )
        except Exception:
            logger.exception(
                "Failed to send email auto-reply for conversation %s",
                conversation.id,
            )
            return None

    async def _is_first_customer_message(self, conversation_id: str, message_id: str) -> bool:
        count = (
            await self.db.execute(
                select(func.count(Message.id)).where(
                    Message.conversation_id == conversation_id,
                    Message.sender_type == SenderType.CUSTOMER,
                )
            )
        ).scalar_one()
        if count != 1:
            return False
        first = (
            await self.db.execute(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_type == SenderType.CUSTOMER,
                )
                .order_by(Message.created_at.asc())
                .limit(1)
            )
        ).scalar_one()
        return first == message_id

    async def _already_sent(self, conversation_id: str) -> bool:
        result = await self.db.execute(
            select(Message.id)
            .where(
                Message.conversation_id == conversation_id,
                Message.metadata_.contains({"auto_responder": True}),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
