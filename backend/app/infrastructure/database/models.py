from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base

__all__ = [
    "ActorType",
    "Attachment",
    "AuditLog",
    "Base",
    "ChannelConfiguration",
    "ChannelType",
    "Conversation",
    "AIControlMode",
    "ConversationStatus",
    "DeliveryStatus",
    "ExternalMessage",
    "TicketSource",
    "Customer",
    "Message",
    "Organization",
    "Participant",
    "Priority",
    "Role",
    "RoleName",
    "SenderType",
    "Team",
    "TeamMember",
    "Ticket",
    "TicketStatus",
    "User",
]


class RoleName(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    AGENT = "AGENT"
    READ_ONLY = "READ_ONLY"


class ChannelType(StrEnum):
    WEB_CHAT = "WEB_CHAT"
    EMAIL = "EMAIL"
    FORM = "FORM"


class ConversationStatus(StrEnum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    WAITING_FOR_AGENT = "WAITING_FOR_AGENT"
    CLOSED = "CLOSED"


class AIControlMode(StrEnum):
    AI_CONTROL = "AI_CONTROL"
    HUMAN_CONTROL = "HUMAN_CONTROL"


class TicketSource(StrEnum):
    AI_ESCALATION = "AI_ESCALATION"
    MISSED_CHAT = "MISSED_CHAT"
    AGENT_CREATED = "AGENT_CREATED"
    HELP_CENTER = "HELP_CENTER"
    AUTOMATION = "AUTOMATION"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class SenderType(StrEnum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"
    AI = "AI"
    SYSTEM = "SYSTEM"


class DeliveryStatus(StrEnum):
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    OPENED = "OPENED"
    FAILED = "FAILED"


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class ActorType(StrEnum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    AI = "AI"
    CUSTOMER = "CUSTOMER"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    logo_url: Mapped[str | None] = mapped_column(String(512))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    teams: Mapped[list["Team"]] = relationship(back_populates="organization")
    customers: Mapped[list["Customer"]] = relationship(back_populates="organization")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="organization")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[RoleName] = mapped_column(Enum(RoleName, name="role_name"), unique=True, nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="users")
    role: Mapped[Role] = relationship(back_populates="users")
    team_memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    last_assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="teams")
    members: Mapped[list["TeamMember"]] = relationship(back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="team_memberships")


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_org_email", "organization_id", "email"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(64))
    company_name: Mapped[str | None] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="customers")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="channel_type"), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"), default=ConversationStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority"), default=Priority.NORMAL)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), index=True)
    subject: Mapped[str | None] = mapped_column(String(512))
    thread_id: Mapped[str | None] = mapped_column(String(512), index=True)
    ai_control_mode: Mapped[AIControlMode] = mapped_column(
        Enum(AIControlMode, name="ai_control_mode"), default=AIControlMode.AI_CONTROL, nullable=False
    )
    conversation_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="conversations")
    customer: Mapped[Customer] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")
    participants: Mapped[list["Participant"]] = relationship(back_populates="conversation")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="conversation")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("conversation_id", "participant_type", "participant_id", name="uq_participant"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    participant_type: Mapped[SenderType] = mapped_column(Enum(SenderType, name="sender_type", create_constraint=False))
    participant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="participants")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    sender_type: Mapped[SenderType] = mapped_column(Enum(SenderType, name="sender_type"), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[ChannelType | None] = mapped_column(Enum(ChannelType, name="channel_type", create_constraint=False))
    external_message_id: Mapped[str | None] = mapped_column(String(512), index=True)
    delivery_status: Mapped[DeliveryStatus | None] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", create_constraint=False)
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="message")


class ExternalMessage(Base):
    """Idempotency record for inbound channel webhooks."""

    __tablename__ = "external_messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "external_message_id", name="uq_external_message_idempotency"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_message_id: Mapped[str] = mapped_column(String(512), nullable=False)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size: Mapped[int] = mapped_column(default=0)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[Message] = relationship(back_populates="attachments")


class ChannelConfiguration(Base):
    __tablename__ = "channel_configurations"
    __table_args__ = (UniqueConstraint("organization_id", "channel", name="uq_channel_configuration_org_channel"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="channel_type", create_constraint=False), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True)
    source: Mapped[TicketSource] = mapped_column(
        Enum(TicketSource, name="ticket_source"), default=TicketSource.AGENT_CREATED, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"), default=TicketStatus.OPEN
    )
    priority: Mapped[Priority] = mapped_column(Enum(Priority, name="priority", create_constraint=False), default=Priority.NORMAL)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="tickets")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType, name="actor_type"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
