from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.infrastructure.database.models import WidgetStatus

DEFAULT_APPEARANCE: dict[str, Any] = {
    "primary_color": "#0F766E",
    "text_color": "#FFFFFF",
    "launcher_position": "bottom-right",
    "launcher_text": "Chat with us",
    "border_radius_px": 16,
    "z_index": 999999,
    "logo_url": None,
}


class WidgetAppearance(BaseModel):
    primary_color: str = "#0F766E"
    text_color: str = "#FFFFFF"
    launcher_position: str = "bottom-right"
    launcher_text: str = "Chat with us"
    border_radius_px: int = 16
    z_index: int = 999999
    logo_url: str | None = None


class WidgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: WidgetStatus = WidgetStatus.DRAFT
    allowed_domains: list[str] = Field(default_factory=list)
    appearance: dict[str, Any] = Field(default_factory=lambda: dict(DEFAULT_APPEARANCE))
    welcome_message: str = "Hi! How can we help?"
    offline_message: str | None = "We're offline right now. Please try again later."
    require_email: bool = False
    require_name: bool = False

    @field_validator("allowed_domains")
    @classmethod
    def _normalize_domains(cls, value: list[str]) -> list[str]:
        return [d.strip().lower() for d in value if d and d.strip()]


class WidgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: WidgetStatus | None = None
    allowed_domains: list[str] | None = None
    appearance: dict[str, Any] | None = None
    welcome_message: str | None = None
    offline_message: str | None = None
    require_email: bool | None = None
    require_name: bool | None = None

    @field_validator("allowed_domains")
    @classmethod
    def _normalize_domains(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [d.strip().lower() for d in value if d and d.strip()]


class WidgetOut(BaseModel):
    id: str
    organization_id: str
    public_id: str
    name: str
    status: WidgetStatus
    allowed_domains: list[Any]
    appearance: dict[str, Any]
    welcome_message: str
    offline_message: str | None
    require_email: bool
    require_name: bool
    ai_settings: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmbedSnippetOut(BaseModel):
    public_id: str
    snippet: str
    widget_js_url: str
    frame_url: str


class PreviewTokenOut(BaseModel):
    preview_token: str
    expires_at: datetime
    frame_url: str


class PublicWidgetConfigOut(BaseModel):
    public_id: str
    name: str
    status: WidgetStatus
    welcome_message: str
    offline_message: str | None
    require_name: bool
    require_email: bool
    appearance: dict[str, Any]


class WidgetSessionCreate(BaseModel):
    visitor_key: str | None = None
    name: str | None = None
    email: str | None = None
    page_url: str | None = None
    page_host: str | None = None


class WidgetSessionOut(BaseModel):
    visitor_key: str
    customer_id: str
    visitor_token: str
    expires_at: datetime
    conversation_id: str | None = None


class WidgetMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WidgetAIResponseCheck(BaseModel):
    message_id: str | None = None
