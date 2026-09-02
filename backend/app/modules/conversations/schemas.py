from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.database.models import AIControlMode, ChannelType, ConversationStatus, Priority, SenderType


class ConversationCreate(BaseModel):
    customer_id: str
    channel: ChannelType = ChannelType.WEB_CHAT
    subject: str | None = None
    priority: Priority = Priority.NORMAL
    initial_message: str | None = None


class ConversationUpdate(BaseModel):
    status: ConversationStatus | None = None
    priority: Priority | None = None
    assigned_user_id: str | None = None
    assigned_team_id: str | None = None
    subject: str | None = None


class ConversationOut(BaseModel):
    id: str
    organization_id: str
    customer_id: str
    channel: ChannelType
    status: ConversationStatus
    priority: Priority
    assigned_user_id: str | None
    assigned_team_id: str | None
    subject: str | None
    ai_control_mode: AIControlMode = AIControlMode.AI_CONTROL
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    sender_type: SenderType = SenderType.AGENT
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublicMessageCreate(BaseModel):
    """Customer web-chat message (no agent auth)."""

    content: str = Field(min_length=1)
    customer_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_type: SenderType
    sender_id: str | None
    content: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class InboxFilter(BaseModel):
    view: str = "all"  # all | mine | unassigned | team


class AIResponseStatusOut(BaseModel):
    status: str
    ticket_id: str | None = None
    timeout_seconds: int


class PublicAIResponseCheck(BaseModel):
    customer_id: str
    message_id: str | None = None
