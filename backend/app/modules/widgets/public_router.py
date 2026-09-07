from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db
from app.modules.conversations.schemas import AIResponseStatusOut, ConversationOut, MessageOut
from app.modules.conversations.service import ConversationService
from app.modules.ai.application.ai_response_timeout_service import AIResponseTimeoutService
from app.modules.widgets.rate_limit import rate_limit_message, rate_limit_session
from app.modules.widgets.schemas import (
    PublicWidgetConfigOut,
    WidgetAIResponseCheck,
    WidgetMessageCreate,
    WidgetSessionCreate,
    WidgetSessionOut,
)
from app.modules.widgets.service import WidgetService
from app.modules.widgets.visitor_token import decode_preview_token, decode_visitor_token

router = APIRouter(prefix="/public/widgets", tags=["public-widgets"])
bearer_scheme = HTTPBearer(auto_error=False)


async def _require_visitor(
    credentials: HTTPAuthorizationCredentials | None,
    *,
    widget_public_id: str,
    widget_id: str,
    organization_id: str,
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Visitor token required")
    try:
        payload = decode_visitor_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid visitor token") from exc
    if payload.get("widget_id") != widget_id and payload.get("widget_public_id") != widget_public_id:
        raise HTTPException(status_code=401, detail="Visitor token widget mismatch")
    if payload.get("org_id") != organization_id:
        raise HTTPException(status_code=401, detail="Visitor token organization mismatch")
    return payload


def _preview_for_widget(preview_token: str | None, widget: object) -> bool:
    if not preview_token:
        return False
    try:
        payload = decode_preview_token(preview_token)
    except ValueError:
        return False
    return (
        payload.get("widget_id") == getattr(widget, "id", None)
        or payload.get("widget_public_id") == getattr(widget, "public_id", None)
    )


@router.get("/{public_id}/config", response_model=PublicWidgetConfigOut)
async def get_public_config(
    public_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
    x_widget_preview_token: str | None = Header(default=None, alias="X-Widget-Preview-Token"),
):
    service = WidgetService(db)
    widget = await service.get_by_public_id(public_id)
    preview = _preview_for_widget(x_widget_preview_token, widget)
    service.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=x_widget_page_host,
        preview=preview,
    )
    return service.public_config(widget)


@router.post("/{public_id}/session", response_model=WidgetSessionOut)
async def create_session(
    public_id: str,
    body: WidgetSessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
    x_widget_preview_token: str | None = Header(default=None, alias="X-Widget-Preview-Token"),
):
    rate_limit_session(request, public_id)
    service = WidgetService(db)
    widget = await service.get_by_public_id(public_id)
    preview = _preview_for_widget(x_widget_preview_token, widget)
    page_host = body.page_host or x_widget_page_host
    service.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=page_host,
        preview=preview,
    )
    return await service.create_or_restore_session(widget, body, preview=preview)


@router.post("/{public_id}/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    public_id: str,
    body: WidgetMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
    x_widget_preview_token: str | None = Header(default=None, alias="X-Widget-Preview-Token"),
):
    rate_limit_message(request, public_id)
    service = WidgetService(db)
    widget = await service.get_by_public_id(public_id)
    preview = _preview_for_widget(x_widget_preview_token, widget)
    service.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=x_widget_page_host,
        preview=preview,
    )
    visitor = await _require_visitor(
        credentials,
        widget_public_id=widget.public_id,
        widget_id=widget.id,
        organization_id=widget.organization_id,
    )
    conversation = await service.create_embed_conversation(
        widget,
        customer_id=visitor["sub"],
        content=body.content,
        metadata=body.metadata,
        preview=preview,
    )
    return conversation


@router.post(
    "/{public_id}/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
async def send_message(
    public_id: str,
    conversation_id: str,
    body: WidgetMessageCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
    x_widget_preview_token: str | None = Header(default=None, alias="X-Widget-Preview-Token"),
):
    rate_limit_message(request, public_id)
    wservice = WidgetService(db)
    widget = await wservice.get_by_public_id(public_id)
    preview = _preview_for_widget(x_widget_preview_token, widget)
    wservice.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=x_widget_page_host,
        preview=preview,
    )
    visitor = await _require_visitor(
        credentials,
        widget_public_id=widget.public_id,
        widget_id=widget.id,
        organization_id=widget.organization_id,
    )
    if widget.status.value != "ACTIVE" and not preview:
        raise HTTPException(status_code=403, detail="Widget is not active")
    await wservice.assert_web_chat_enabled(widget.organization_id)

    cservice = ConversationService(db)
    conv = await cservice.get_conversation(widget.organization_id, conversation_id)
    if conv.customer_id != visitor["sub"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.widget_id and conv.widget_id != widget.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message = await cservice.add_public_message(
        conversation_id,
        visitor["sub"],
        body.content,
        {
            **body.metadata,
            "source": "embed",
            "widget_public_id": widget.public_id,
        },
    )
    enriched = await cservice.enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.get(
    "/{public_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
async def list_messages(
    public_id: str,
    conversation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
):
    wservice = WidgetService(db)
    widget = await wservice.get_by_public_id(public_id)
    wservice.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=x_widget_page_host,
    )
    visitor = await _require_visitor(
        credentials,
        widget_public_id=widget.public_id,
        widget_id=widget.id,
        organization_id=widget.organization_id,
    )
    cservice = ConversationService(db)
    conv = await cservice.get_conversation(widget.organization_id, conversation_id)
    if conv.customer_id != visitor["sub"]:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.widget_id and conv.widget_id != widget.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await cservice.list_public_messages(conversation_id, visitor["sub"])
    return [MessageOut.model_validate(await cservice.enrich_message(m)) for m in messages]


@router.post(
    "/{public_id}/conversations/{conversation_id}/check-ai-response",
    response_model=AIResponseStatusOut,
)
async def check_ai_response(
    public_id: str,
    conversation_id: str,
    body: WidgetAIResponseCheck,
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_widget_page_host: str | None = Header(default=None, alias="X-Widget-Page-Host"),
):
    wservice = WidgetService(db)
    widget = await wservice.get_by_public_id(public_id)
    wservice.assert_domain_allowed(
        widget,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
        page_host=x_widget_page_host,
    )
    visitor = await _require_visitor(
        credentials,
        widget_public_id=widget.public_id,
        widget_id=widget.id,
        organization_id=widget.organization_id,
    )
    cservice = ConversationService(db)
    conv = await cservice.get_conversation(widget.organization_id, conversation_id)
    if conv.customer_id != visitor["sub"]:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await AIResponseTimeoutService(db).check_or_escalate(
        conversation_id,
        visitor["sub"],
        message_id=body.message_id,
    )
    await db.commit()
    return AIResponseStatusOut.model_validate(result)
