from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.infrastructure.database.models import ChannelType, DeliveryStatus


class ChannelConfigurationOut(BaseModel):
    id: str
    organization_id: str
    channel: ChannelType
    enabled: bool
    provider: str | None
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChannelConfigurationUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    settings: dict[str, Any] | None = None


class AttachmentOut(BaseModel):
    id: str
    message_id: str | None
    filename: str
    mime_type: str
    size: int
    storage_key: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    download_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class EmailSendRequest(BaseModel):
    subject: str | None = None
    content: str = Field(min_length=1)
    attachment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedChannelMessage(BaseModel):
    """Channel-agnostic internal message shape."""

    channel: ChannelType
    sender_type: str
    content: str
    external_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageOutExtended(BaseModel):
    id: str
    conversation_id: str
    sender_type: str
    sender_id: str | None
    content: str
    channel: ChannelType | None = None
    external_message_id: str | None = None
    delivery_status: DeliveryStatus | None = None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    attachments: list[AttachmentOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
