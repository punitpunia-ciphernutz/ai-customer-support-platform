from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.infrastructure.database.models import (
    ChannelConfiguration,
    ChannelType,
    ChatWidget,
    Conversation,
    ConversationStatus,
    Customer,
    Priority,
    WidgetStatus,
)
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService
from app.modules.customers.resolver import CustomerResolver
from app.modules.widgets.domain_guard import extract_request_host, host_matches_allowlist
from app.modules.widgets.schemas import (
    DEFAULT_APPEARANCE,
    EmbedSnippetOut,
    PreviewTokenOut,
    PublicWidgetConfigOut,
    WidgetCreate,
    WidgetSessionCreate,
    WidgetSessionOut,
    WidgetUpdate,
)
from app.modules.widgets.visitor_token import (
    create_preview_token,
    create_visitor_token,
    visitor_ttl_minutes,
)


def generate_public_id() -> str:
    return f"wgt_{secrets.token_urlsafe(12)}"


class WidgetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_widgets(self, organization_id: str) -> list[ChatWidget]:
        result = await self.db.execute(
            select(ChatWidget)
            .where(ChatWidget.organization_id == organization_id)
            .order_by(ChatWidget.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_widget(self, organization_id: str, widget_id: str) -> ChatWidget:
        result = await self.db.execute(
            select(ChatWidget).where(
                ChatWidget.id == widget_id,
                ChatWidget.organization_id == organization_id,
            )
        )
        widget = result.scalar_one_or_none()
        if widget is None:
            raise HTTPException(status_code=404, detail="Widget not found")
        return widget

    async def get_by_public_id(self, public_id: str) -> ChatWidget:
        result = await self.db.execute(select(ChatWidget).where(ChatWidget.public_id == public_id))
        widget = result.scalar_one_or_none()
        if widget is None:
            raise HTTPException(status_code=404, detail="Widget not found")
        return widget

    def _validate_active_domains(self, widget_status: WidgetStatus, domains: list[str]) -> None:
        if widget_status == WidgetStatus.ACTIVE and not domains:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ACTIVE widgets require at least one allowed domain",
            )

    async def create_widget(self, organization_id: str, body: WidgetCreate) -> ChatWidget:
        self._validate_active_domains(body.status, body.allowed_domains)
        appearance = {**DEFAULT_APPEARANCE, **(body.appearance or {})}
        widget = ChatWidget(
            organization_id=organization_id,
            public_id=generate_public_id(),
            name=body.name.strip(),
            status=body.status,
            allowed_domains=body.allowed_domains,
            appearance=appearance,
            welcome_message=body.welcome_message,
            offline_message=body.offline_message,
            require_email=body.require_email,
            require_name=body.require_name,
        )
        self.db.add(widget)
        await self.db.flush()
        await self.db.refresh(widget)
        return widget

    async def update_widget(
        self, organization_id: str, widget_id: str, body: WidgetUpdate
    ) -> ChatWidget:
        widget = await self.get_widget(organization_id, widget_id)
        data = body.model_dump(exclude_unset=True)
        new_status = data.get("status", widget.status)
        new_domains = data.get("allowed_domains", widget.allowed_domains or [])
        self._validate_active_domains(new_status, list(new_domains))
        for key, value in data.items():
            if key == "appearance" and isinstance(value, dict):
                setattr(widget, key, {**(widget.appearance or {}), **value})
            else:
                setattr(widget, key, value)
        await self.db.flush()
        await self.db.refresh(widget)
        return widget

    async def delete_widget(self, organization_id: str, widget_id: str) -> None:
        widget = await self.get_widget(organization_id, widget_id)
        referenced = await self.db.scalar(
            select(Conversation.id).where(Conversation.widget_id == widget.id).limit(1)
        )
        if referenced is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Widget has conversations; set status to INACTIVE instead of deleting",
            )
        await self.db.delete(widget)
        await self.db.flush()

    def build_embed_snippet(self, widget: ChatWidget) -> EmbedSnippetOut:
        settings = get_settings()
        base = settings.frontend_public_url.rstrip("/")
        widget_js_url = f"{base}/widget.js"
        frame_url = f"{base}/widget-frame.html?widget_id={widget.public_id}"
        snippet = (
            "<!-- Support Platform Chat -->\n"
            f'<script async src="{widget_js_url}" data-widget-id="{widget.public_id}"></script>'
        )
        return EmbedSnippetOut(
            public_id=widget.public_id,
            snippet=snippet,
            widget_js_url=widget_js_url,
            frame_url=frame_url,
        )

    async def create_preview_token_for(
        self, organization_id: str, widget_id: str, user_id: str
    ) -> PreviewTokenOut:
        widget = await self.get_widget(organization_id, widget_id)
        token, expires_at = create_preview_token(
            organization_id=organization_id,
            widget_id=widget.id,
            widget_public_id=widget.public_id,
            user_id=user_id,
        )
        settings = get_settings()
        base = settings.frontend_public_url.rstrip("/")
        frame_url = (
            f"{base}/widget-frame.html?widget_id={widget.public_id}"
            f"&preview_token={token}&page_host=localhost"
        )
        return PreviewTokenOut(preview_token=token, expires_at=expires_at, frame_url=frame_url)

    async def assert_web_chat_enabled(self, organization_id: str) -> None:
        cfg = await self.db.scalar(
            select(ChannelConfiguration).where(
                ChannelConfiguration.organization_id == organization_id,
                ChannelConfiguration.channel == ChannelType.WEB_CHAT,
            )
        )
        if cfg is None or not cfg.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WEB_CHAT channel is disabled",
            )

    def assert_domain_allowed(
        self,
        widget: ChatWidget,
        *,
        origin: str | None = None,
        referer: str | None = None,
        page_host: str | None = None,
        preview: bool = False,
    ) -> str:
        if preview:
            host = extract_request_host(origin=origin, referer=referer, page_host=page_host) or "localhost"
            if host in {"localhost", "127.0.0.1"} or host_matches_allowlist(
                host, list(widget.allowed_domains or [])
            ):
                return host
            raise HTTPException(status_code=403, detail="Domain not allowed for preview")

        host = extract_request_host(origin=origin, referer=referer, page_host=page_host)
        if not host_matches_allowlist(host, list(widget.allowed_domains or [])):
            raise HTTPException(status_code=403, detail="Domain not allowed for this widget")
        return host  # type: ignore[return-value]

    def public_config(self, widget: ChatWidget) -> PublicWidgetConfigOut:
        if widget.status == WidgetStatus.DRAFT:
            raise HTTPException(status_code=404, detail="Widget not found")
        return PublicWidgetConfigOut(
            public_id=widget.public_id,
            name=widget.name,
            status=widget.status,
            welcome_message=widget.welcome_message,
            offline_message=widget.offline_message,
            require_name=widget.require_name,
            require_email=widget.require_email,
            appearance=widget.appearance or dict(DEFAULT_APPEARANCE),
        )

    async def create_or_restore_session(
        self,
        widget: ChatWidget,
        body: WidgetSessionCreate,
        *,
        preview: bool = False,
    ) -> WidgetSessionOut:
        if widget.status != WidgetStatus.ACTIVE and not preview:
            raise HTTPException(status_code=403, detail="Widget is not active")
        await self.assert_web_chat_enabled(widget.organization_id)

        if widget.require_email and not (body.email and body.email.strip()):
            raise HTTPException(status_code=400, detail="Email is required")
        if widget.require_name and not (body.name and body.name.strip()):
            raise HTTPException(status_code=400, detail="Name is required")

        resolver = CustomerResolver(self.db)
        visitor_key = (body.visitor_key or "").strip() or str(uuid4())
        external_id = f"widget:{widget.public_id}:vid:{visitor_key}"

        if body.email and body.email.strip():
            customer = await resolver.resolve_by_email(
                widget.organization_id,
                body.email,
                name=body.name,
            )
            # Keep visitor linkage for anonymous restore if email path later
            if not customer.external_id:
                customer.external_id = external_id
                meta = dict(customer.metadata_ or {})
                meta["widget_visitor_key"] = visitor_key
                meta["widget_public_id"] = widget.public_id
                customer.metadata_ = meta
                await self.db.flush()
        else:
            customer = await resolver.resolve_anonymous_visitor(
                widget.organization_id,
                external_id=external_id,
                name=body.name or "Visitor",
                metadata={
                    "widget_visitor_key": visitor_key,
                    "widget_public_id": widget.public_id,
                    "page_url": body.page_url,
                    "page_host": body.page_host,
                },
            )

        conversation = await self.find_resumable_conversation(customer.id, widget.id)
        token, expires_at = create_visitor_token(
            customer_id=customer.id,
            organization_id=widget.organization_id,
            widget_id=widget.id,
            widget_public_id=widget.public_id,
            conversation_id=conversation.id if conversation else None,
            expires_minutes=visitor_ttl_minutes(),
        )
        return WidgetSessionOut(
            visitor_key=visitor_key,
            customer_id=customer.id,
            visitor_token=token,
            expires_at=expires_at,
            conversation_id=conversation.id if conversation else None,
        )

    async def find_resumable_conversation(
        self, customer_id: str, widget_id: str
    ) -> Conversation | None:
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(days=settings.widget_resume_days)
        result = await self.db.execute(
            select(Conversation)
            .where(
                Conversation.customer_id == customer_id,
                Conversation.widget_id == widget_id,
                Conversation.status != ConversationStatus.CLOSED,
                Conversation.updated_at >= cutoff,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_embed_conversation(
        self,
        widget: ChatWidget,
        *,
        customer_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        preview: bool = False,
    ) -> Conversation:
        if widget.status != WidgetStatus.ACTIVE and not preview:
            raise HTTPException(status_code=403, detail="Widget is not active")
        await self.assert_web_chat_enabled(widget.organization_id)

        existing = await self.find_resumable_conversation(customer_id, widget.id)
        if existing is not None:
            await ConversationService(self.db).add_public_message(
                existing.id,
                customer_id,
                content,
                {
                    **(metadata or {}),
                    "source": "embed",
                    "widget_public_id": widget.public_id,
                },
            )
            await self.db.refresh(existing)
            return existing

        body = ConversationCreate(
            customer_id=customer_id,
            channel=ChannelType.WEB_CHAT,
            priority=Priority.NORMAL,
            initial_message=content,
        )
        return await ConversationService(self.db).create_public_conversation(
            body,
            widget_id=widget.id,
            message_metadata={
                **(metadata or {}),
                "source": "embed",
                "widget_public_id": widget.public_id,
            },
        )
