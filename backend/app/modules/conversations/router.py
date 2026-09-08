from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import Conversation, Message, User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.channels.schemas import EmailSendRequest
from app.modules.conversations.schemas import (
    AIResponseStatusOut,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
    PublicAIResponseCheck,
    PublicMessageCreate,
)
from app.modules.conversations.serialize import conversation_to_out
from app.modules.conversations.service import ConversationService
from app.modules.tags.application.service import TagService
from app.modules.tickets.schemas import TicketOut
from app.modules.tickets.serialize import ticket_to_out

router = APIRouter(tags=["conversations"])


async def _conversations_with_tags(
    db: AsyncSession, conversations: list[Conversation]
) -> list[ConversationOut]:
    tag_map = await TagService(db).map_effective_conversation_tags([c.id for c in conversations])
    return [conversation_to_out(c, tag_map.get(c.id, [])) for c in conversations]


async def _conversation_with_tags(db: AsyncSession, conversation: Conversation) -> ConversationOut:
    tag_map = await TagService(db).map_effective_conversation_tags([conversation.id])
    return conversation_to_out(conversation, tag_map.get(conversation.id, []))


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    view: str = Query("all"),
    tag: list[str] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[ConversationOut]:
    conversations = await ConversationService(db).list_conversations(user, view=view)
    outs = await _conversations_with_tags(db, conversations)
    tag_filters = [t.strip().lower() for t in (tag or []) if t and t.strip()]
    if tag_filters:
        outs = [c for c in outs if all(t in c.tags for t in tag_filters)]
    return outs


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await ConversationService(db).create_conversation(user, body)
    return await _conversation_with_tags(db, conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> ConversationOut:
    conversation = await ConversationService(db).get_conversation(user.organization_id, conversation_id)
    return await _conversation_with_tags(db, conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await ConversationService(db).update_conversation(user, conversation_id, body)
    return await _conversation_with_tags(db, conversation)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[MessageOut]:
    enriched = await ConversationService(db).list_messages_enriched(user.organization_id, conversation_id)
    return [MessageOut.model_validate(item) for item in enriched]


@router.post("/conversations/{conversation_id}/email", response_model=MessageOut, status_code=201)
async def send_email(
    conversation_id: str,
    body: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> MessageOut:
    message = await ConversationService(db).send_email_reply(user, conversation_id, body)
    enriched = await ConversationService(db).enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> MessageOut:
    message = await ConversationService(db).add_agent_message(user, conversation_id, body)
    enriched = await ConversationService(db).enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.post("/public/conversations", response_model=ConversationOut, status_code=201)
async def public_create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    """Unauthenticated web-chat entry: create conversation for an existing customer."""
    return await ConversationService(db).create_public_conversation(body)


@router.post(
    "/public/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
async def public_create_message(
    conversation_id: str,
    body: PublicMessageCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    service = ConversationService(db)
    message = await service.add_public_message(
        conversation_id, body.customer_id, body.content, body.metadata
    )
    enriched = await service.enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.get("/public/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def public_list_messages(
    conversation_id: str,
    customer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    service = ConversationService(db)
    messages = await service.list_public_messages(conversation_id, customer_id)
    return [MessageOut.model_validate(await service.enrich_message(message)) for message in messages]


@router.post(
    "/public/conversations/{conversation_id}/check-ai-response",
    response_model=AIResponseStatusOut,
)
async def public_check_ai_response(
    conversation_id: str,
    body: PublicAIResponseCheck,
    db: AsyncSession = Depends(get_db),
) -> AIResponseStatusOut:
    from app.modules.ai.application.ai_response_timeout_service import AIResponseTimeoutService

    result = await AIResponseTimeoutService(db).check_or_escalate(
        conversation_id,
        body.customer_id,
        message_id=body.message_id,
    )
    await db.commit()
    return AIResponseStatusOut.model_validate(result)


@router.get("/conversations/{conversation_id}/ai-usage")
async def get_conversation_ai_usage(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
):
    from app.modules.ai.application.usage_service import AIUsageService

    return await AIUsageService(db).get_conversation_summary(user.organization_id, conversation_id)


@router.post("/conversations/{conversation_id}/takeover", response_model=ConversationOut)
async def takeover_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await ConversationService(db).takeover(user, conversation_id)
    return await _conversation_with_tags(db, conversation)


@router.post("/conversations/{conversation_id}/return-to-ai", response_model=ConversationOut)
async def return_conversation_to_ai(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> ConversationOut:
    conversation = await ConversationService(db).return_to_ai(user, conversation_id)
    return await _conversation_with_tags(db, conversation)


@router.post("/conversations/{conversation_id}/ticket", status_code=201, response_model=TicketOut)
async def create_conversation_ticket(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> TicketOut:
    ticket = await ConversationService(db).create_ticket_from_conversation(user, conversation_id)
    service = TagService(db)
    for tag_name in await service.list_conversation_tags(conversation_id):
        await service.add_ticket_tag(user.organization_id, ticket.id, tag_name)
    tags = await service.list_ticket_tags(ticket.id)
    return ticket_to_out(ticket, tags)


@router.post("/conversations/{conversation_id}/suggestions/{message_id}/accept", response_model=MessageOut)
async def accept_suggestion(
    conversation_id: str,
    message_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> MessageOut:
    service = ConversationService(db)
    message = await service.update_suggestion_status(
        user, conversation_id, message_id, "accepted", event="suggestion.accepted"
    )
    enriched = await service.enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.post("/conversations/{conversation_id}/suggestions/{message_id}/reject", response_model=MessageOut)
async def reject_suggestion(
    conversation_id: str,
    message_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> MessageOut:
    service = ConversationService(db)
    message = await service.update_suggestion_status(
        user, conversation_id, message_id, "rejected", event="suggestion.rejected"
    )
    enriched = await service.enrich_message(message)
    return MessageOut.model_validate(enriched)


@router.post("/conversations/{conversation_id}/suggestions/{message_id}/regenerate", response_model=MessageOut)
async def regenerate_suggestion(
    conversation_id: str,
    message_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> MessageOut:
    service = ConversationService(db)
    message = await service.regenerate_suggestion(user, conversation_id, message_id)
    enriched = await service.enrich_message(message)
    return MessageOut.model_validate(enriched)
