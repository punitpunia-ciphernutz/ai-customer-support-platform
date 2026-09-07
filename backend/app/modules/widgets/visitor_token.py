"""Visitor JWT helpers for embeddable chat widgets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.modules.auth.security import create_access_token, decode_access_token

VISITOR_TOKEN_TYPE = "visitor"
PREVIEW_TOKEN_TYPE = "widget_preview"
DEFAULT_VISITOR_TTL_MINUTES = 60 * 24  # 24h
DEFAULT_PREVIEW_TTL_MINUTES = 30


def create_visitor_token(
    *,
    customer_id: str,
    organization_id: str,
    widget_id: str,
    widget_public_id: str,
    conversation_id: str | None = None,
    expires_minutes: int = DEFAULT_VISITOR_TTL_MINUTES,
) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    extra: dict[str, Any] = {
        "typ": VISITOR_TOKEN_TYPE,
        "org_id": organization_id,
        "widget_id": widget_id,
        "widget_public_id": widget_public_id,
        "exp": expires_at,
    }
    if conversation_id:
        extra["conversation_id"] = conversation_id
    token = create_access_token(customer_id, extra=extra, expires_minutes=expires_minutes)
    return token, expires_at


def create_preview_token(
    *,
    organization_id: str,
    widget_id: str,
    widget_public_id: str,
    user_id: str,
    expires_minutes: int = DEFAULT_PREVIEW_TTL_MINUTES,
) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    token = create_access_token(
        user_id,
        extra={
            "typ": PREVIEW_TOKEN_TYPE,
            "org_id": organization_id,
            "widget_id": widget_id,
            "widget_public_id": widget_public_id,
            "exp": expires_at,
        },
        expires_minutes=expires_minutes,
    )
    return token, expires_at


def decode_visitor_token(token: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    if payload.get("typ") != VISITOR_TOKEN_TYPE:
        raise ValueError("Not a visitor token")
    if not payload.get("sub") or not payload.get("org_id") or not payload.get("widget_id"):
        raise ValueError("Incomplete visitor token")
    return payload


def decode_preview_token(token: str) -> dict[str, Any]:
    payload = decode_access_token(token)
    if payload.get("typ") != PREVIEW_TOKEN_TYPE:
        raise ValueError("Not a preview token")
    return payload


def visitor_ttl_minutes() -> int:
    settings = get_settings()
    return int(getattr(settings, "visitor_token_expire_minutes", DEFAULT_VISITOR_TTL_MINUTES))
