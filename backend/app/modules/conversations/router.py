from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import Conversation, Message, User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
    PublicMessageCreate,
)
from app.modules.conversations.service import ConversationService

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    view: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[Conversation]:
    return await ConversationService(db).list_conversations(user, view=view)


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Conversation:
    return await ConversationService(db).create_conversation(user, body)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> Conversation:
    return await ConversationService(db).get_conversation(user.organization_id, conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Conversation:
    return await ConversationService(db).update_conversation(user, conversation_id, body)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[Message]:
    return await ConversationService(db).list_messages(user.organization_id, conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Message:
    return await ConversationService(db).add_agent_message(user, conversation_id, body)


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
) -> Message:
    return await ConversationService(db).add_public_message(
        conversation_id, body.customer_id, body.content, body.metadata
    )


@router.get("/public/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def public_list_messages(
    conversation_id: str,
    customer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    return await ConversationService(db).list_public_messages(conversation_id, customer_id)
