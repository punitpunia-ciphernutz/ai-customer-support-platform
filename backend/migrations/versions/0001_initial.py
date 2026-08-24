"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str) -> postgresql.ENUM:
    """Reuse existing PG enum types; do not auto-create on table DDL."""
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    role_name = _enum("OWNER", "ADMIN", "MANAGER", "AGENT", "READ_ONLY", name="role_name")
    channel_type = _enum("WEB_CHAT", "EMAIL", "FORM", name="channel_type")
    conversation_status = _enum("OPEN", "PENDING", "CLOSED", name="conversation_status")
    priority = _enum("LOW", "NORMAL", "HIGH", "URGENT", name="priority")
    sender_type = _enum("CUSTOMER", "AGENT", "AI", "SYSTEM", name="sender_type")
    ticket_status = _enum(
        "OPEN", "IN_PROGRESS", "WAITING", "RESOLVED", "CLOSED", name="ticket_status"
    )
    actor_type = _enum("USER", "SYSTEM", "AI", "CUSTOMER", name="actor_type")

    bind = op.get_bind()
    for enum in (
        role_name,
        channel_type,
        conversation_status,
        priority,
        sender_type,
        ticket_status,
        actor_type,
    ):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(255)),
        sa.Column("timezone", sa.String(64), server_default="UTC"),
        sa.Column("logo_url", sa.String(512)),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", role_name, nullable=False, unique=True),
        sa.Column("permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("role_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(64)),
        sa.Column("company_name", sa.String(255)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_organization_id", "customers", ["organization_id"])
    op.create_index("ix_customers_org_email", "customers", ["organization_id", "email"])

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column("channel", channel_type, nullable=False),
        sa.Column("status", conversation_status, server_default="OPEN"),
        sa.Column("priority", priority, server_default="NORMAL"),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("assigned_team_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("teams.id")),
        sa.Column("subject", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_conversations_organization_id", "conversations", ["organization_id"])
    op.create_index("ix_conversations_customer_id", "conversations", ["customer_id"])

    op.create_table(
        "participants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("participant_type", sender_type, nullable=False),
        sa.Column("participant_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "conversation_id", "participant_type", "participant_id", name="uq_participant"
        ),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("sender_type", sender_type, nullable=False),
        sa.Column("sender_id", sa.String(64)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("status", ticket_status, server_default="OPEN"),
        sa.Column("priority", priority, server_default="NORMAL"),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("assigned_team_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("teams.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column("actor_id", sa.String(64)),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("old_value", postgresql.JSONB()),
        sa.Column("new_value", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("tickets")
    op.drop_table("messages")
    op.drop_table("participants")
    op.drop_table("conversations")
    op.drop_table("customers")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("users")
    op.drop_table("roles")
    op.drop_table("organizations")
    bind = op.get_bind()
    for name in (
        "actor_type",
        "ticket_status",
        "sender_type",
        "priority",
        "conversation_status",
        "channel_type",
        "role_name",
    ):
        postgresql.ENUM(name=name, create_type=False).drop(bind, checkfirst=True)
