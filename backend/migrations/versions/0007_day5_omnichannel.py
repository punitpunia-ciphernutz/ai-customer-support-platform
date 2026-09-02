"""Day 5 omnichannel: attachments, channel config, message delivery, idempotency

Revision ID: 0007_day5_omnichannel
Revises: 0006_ai_response_timeout
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_day5_omnichannel"
down_revision: Union[str, None] = "0006_ai_response_timeout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    delivery_status = postgresql.ENUM(
        "QUEUED",
        "SENDING",
        "SENT",
        "DELIVERED",
        "OPENED",
        "FAILED",
        name="delivery_status",
        create_type=True,
    )
    delivery_status.create(bind, checkfirst=True)

    channel_type = postgresql.ENUM("WEB_CHAT", "EMAIL", "FORM", name="channel_type", create_type=False)

    op.add_column(
        "messages",
        sa.Column("channel", channel_type, nullable=True),
    )
    op.add_column("messages", sa.Column("external_message_id", sa.String(512), nullable=True))
    op.add_column(
        "messages",
        sa.Column("delivery_status", delivery_status, nullable=True),
    )
    op.create_index("ix_messages_external_message_id", "messages", ["external_message_id"])

    op.add_column("conversations", sa.Column("thread_id", sa.String(512), nullable=True))
    op.create_index("ix_conversations_thread_id", "conversations", ["thread_id"])

    op.create_table(
        "external_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_message_id", sa.String(512), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "provider", "external_message_id", name="uq_external_message_idempotency"),
    )
    op.create_index("ix_external_messages_org", "external_messages", ["organization_id"])

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("messages.id"), nullable=True, index=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "channel_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("channel", channel_type, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "channel", name="uq_channel_configuration_org_channel"),
    )
    op.create_index("ix_channel_configurations_org", "channel_configurations", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_configurations_org", table_name="channel_configurations")
    op.drop_table("channel_configurations")
    op.drop_table("attachments")
    op.drop_index("ix_external_messages_org", table_name="external_messages")
    op.drop_table("external_messages")
    op.drop_index("ix_conversations_thread_id", table_name="conversations")
    op.drop_column("conversations", "thread_id")
    op.drop_index("ix_messages_external_message_id", table_name="messages")
    op.drop_column("messages", "delivery_status")
    op.drop_column("messages", "external_message_id")
    op.drop_column("messages", "channel")
    op.execute("DROP TYPE IF EXISTS delivery_status")
