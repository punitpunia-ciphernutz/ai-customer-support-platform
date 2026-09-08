"""Serialize conversations with tag names for API responses."""

from __future__ import annotations

from app.infrastructure.database.models import Conversation
from app.modules.conversations.schemas import ConversationOut


def conversation_to_out(conversation: Conversation, tags: list[str] | None = None) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        organization_id=conversation.organization_id,
        customer_id=conversation.customer_id,
        widget_id=conversation.widget_id,
        channel=conversation.channel,
        status=conversation.status,
        priority=conversation.priority,
        assigned_user_id=conversation.assigned_user_id,
        assigned_team_id=conversation.assigned_team_id,
        subject=conversation.subject,
        ai_control_mode=conversation.ai_control_mode,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        tags=list(tags or []),
    )
