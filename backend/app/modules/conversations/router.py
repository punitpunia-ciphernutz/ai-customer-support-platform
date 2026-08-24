from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import (
    ActorType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    Participant,
    SenderType,
    TeamMember,
    User,
)
from app.infrastructure.database.session import get_db
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.auth.permissions import CONVERSATIONS_ASSIGN, CONVERSATIONS_READ, CONVERSATIONS_WRITE
from app.modules.conversations.channels import get_adapter
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
    PublicMessageCreate,
)

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    view: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.organization_id == user.organization_id)
    if view == "mine":
        stmt = stmt.where(Conversation.assigned_user_id == user.id)
    elif view == "unassigned":
        stmt = stmt.where(Conversation.assigned_user_id.is_(None))
    elif view == "team":
        team_ids = (
            await db.execute(select(TeamMember.team_id).where(TeamMember.user_id == user.id))
        ).scalars().all()
        stmt = stmt.where(Conversation.assigned_team_id.in_(list(team_ids) or ["__none__"]))
    stmt = stmt.order_by(Conversation.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Conversation:
    customer = await _get_customer(db, user.organization_id, body.customer_id)
    adapter = get_adapter(body.channel)
    _ = adapter  # validates channel is supported

    conversation = Conversation(
        organization_id=user.organization_id,
        customer_id=customer.id,
        channel=body.channel,
        status=ConversationStatus.OPEN,
        priority=body.priority,
        subject=body.subject,
    )
    db.add(conversation)
    await db.flush()
    db.add(
        Participant(
            conversation_id=conversation.id,
            participant_type=SenderType.CUSTOMER,
            participant_id=customer.id,
        )
    )
    if body.initial_message:
        msg = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=customer.id,
            content=body.initial_message,
            metadata_={},
        )
        db.add(msg)
        await db.flush()
        await event_bus.publish(
            DomainEvent(
                name="message.created",
                organization_id=user.organization_id,
                payload=_message_payload(msg, conversation.id),
            )
        )
    await db.refresh(conversation)
    await event_bus.publish(
        DomainEvent(
            name="conversation.created",
            organization_id=user.organization_id,
            payload={"conversation_id": conversation.id, "customer_id": customer.id},
        )
    )
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> Conversation:
    return await _get_conversation(db, user.organization_id, conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Conversation:
    conversation = await _get_conversation(db, user.organization_id, conversation_id)
    old = {
        "status": conversation.status.value,
        "priority": conversation.priority.value,
        "assigned_user_id": conversation.assigned_user_id,
        "assigned_team_id": conversation.assigned_team_id,
    }
    data = body.model_dump(exclude_unset=True)

    if "assigned_user_id" in data or "assigned_team_id" in data:
        # assign requires extra permission when changing assignee
        perms = set(user.role.permissions or [])
        if CONVERSATIONS_ASSIGN not in perms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing assign permission")

    for key, value in data.items():
        setattr(conversation, key, value)
    await db.flush()
    await db.refresh(conversation)

    new = {
        "status": conversation.status.value,
        "priority": conversation.priority.value,
        "assigned_user_id": conversation.assigned_user_id,
        "assigned_team_id": conversation.assigned_team_id,
    }

    event_name = "conversation.updated"
    if old["assigned_user_id"] != new["assigned_user_id"] or old["assigned_team_id"] != new["assigned_team_id"]:
        event_name = "conversation.assigned"
        await write_audit(
            db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="conversation.assigned",
            entity_type="conversation",
            entity_id=conversation.id,
            old_value=old,
            new_value=new,
        )
    if old["status"] != ConversationStatus.CLOSED.value and new["status"] == ConversationStatus.CLOSED.value:
        event_name = "conversation.closed"
        await write_audit(
            db,
            organization_id=user.organization_id,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="conversation.closed",
            entity_type="conversation",
            entity_id=conversation.id,
            old_value=old,
            new_value=new,
        )

    await event_bus.publish(
        DomainEvent(
            name=event_name,
            organization_id=user.organization_id,
            payload={"conversation_id": conversation.id, **new},
        )
    )
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> list[Message]:
    await _get_conversation(db, user.organization_id, conversation_id)
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def create_message(
    conversation_id: str,
    body: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_WRITE)),
) -> Message:
    conversation = await _get_conversation(db, user.organization_id, conversation_id)
    sender_id = user.id if body.sender_type == SenderType.AGENT else body.metadata.get("sender_id")
    msg = Message(
        conversation_id=conversation.id,
        sender_type=body.sender_type,
        sender_id=sender_id,
        content=body.content,
        metadata_=body.metadata,
    )
    db.add(msg)
    conversation.status = (
        ConversationStatus.OPEN if conversation.status == ConversationStatus.CLOSED else conversation.status
    )
    await db.flush()
    await db.refresh(msg)
    await event_bus.publish(
        DomainEvent(
            name="message.created",
            organization_id=user.organization_id,
            payload=_message_payload(msg, conversation.id),
        )
    )
    await event_bus.publish(
        DomainEvent(
            name="conversation.updated",
            organization_id=user.organization_id,
            payload={"conversation_id": conversation.id},
        )
    )
    return msg


@router.post("/public/conversations", response_model=ConversationOut, status_code=201)
async def public_create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    """Unauthenticated web-chat entry: create conversation for an existing customer."""
    customer = await db.execute(select(Customer).where(Customer.id == body.customer_id))
    cust = customer.scalar_one_or_none()
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    conversation = Conversation(
        organization_id=cust.organization_id,
        customer_id=cust.id,
        channel=body.channel,
        status=ConversationStatus.OPEN,
        priority=body.priority,
        subject=body.subject,
    )
    db.add(conversation)
    await db.flush()
    db.add(
        Participant(
            conversation_id=conversation.id,
            participant_type=SenderType.CUSTOMER,
            participant_id=cust.id,
        )
    )
    if body.initial_message:
        msg = Message(
            conversation_id=conversation.id,
            sender_type=SenderType.CUSTOMER,
            sender_id=cust.id,
            content=body.initial_message,
            metadata_={},
        )
        db.add(msg)
        await db.flush()
        await event_bus.publish(
            DomainEvent(
                name="message.created",
                organization_id=cust.organization_id,
                payload=_message_payload(msg, conversation.id),
            )
        )
    await db.refresh(conversation)
    await event_bus.publish(
        DomainEvent(
            name="conversation.created",
            organization_id=cust.organization_id,
            payload={"conversation_id": conversation.id, "customer_id": cust.id},
        )
    )
    return conversation


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
    result = await db.execute(
        select(Conversation).options(selectinload(Conversation.customer)).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None or conversation.customer_id != body.customer_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msg = Message(
        conversation_id=conversation.id,
        sender_type=SenderType.CUSTOMER,
        sender_id=body.customer_id,
        content=body.content,
        metadata_=body.metadata,
    )
    db.add(msg)
    if conversation.status == ConversationStatus.CLOSED:
        conversation.status = ConversationStatus.OPEN
    await db.flush()
    await db.refresh(msg)
    await event_bus.publish(
        DomainEvent(
            name="message.created",
            organization_id=conversation.organization_id,
            payload=_message_payload(msg, conversation.id),
        )
    )
    return msg


@router.get("/public/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def public_list_messages(
    conversation_id: str,
    customer_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    if conversation is None or conversation.customer_id != customer_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
    )
    return list(msgs.scalars().all())


async def _get_customer(db: AsyncSession, org_id: str, customer_id: str) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


async def _get_conversation(db: AsyncSession, org_id: str, conversation_id: str) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.organization_id == org_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _message_payload(msg: Message, conversation_id: str) -> dict:
    return {
        "message_id": msg.id,
        "conversation_id": conversation_id,
        "sender_type": msg.sender_type.value,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
