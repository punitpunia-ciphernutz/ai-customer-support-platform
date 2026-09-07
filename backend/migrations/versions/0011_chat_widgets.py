"""Add chat_widgets table and conversations.widget_id.

Revision ID: 0011_chat_widgets
Revises: 0010_response_policy
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_chat_widgets"
down_revision: Union[str, None] = "0010_response_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

widget_status = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "INACTIVE",
    name="widget_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE widget_status AS ENUM ('DRAFT', 'ACTIVE', 'INACTIVE'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    )

    op.create_table(
        "chat_widgets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", widget_status, nullable=False, server_default="DRAFT"),
        sa.Column(
            "allowed_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "appearance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("welcome_message", sa.Text(), nullable=False, server_default="Hi! How can we help?"),
        sa.Column("offline_message", sa.Text(), nullable=True),
        sa.Column("require_email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("require_name", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("ai_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_chat_widgets_org", "chat_widgets", ["organization_id"])
    op.create_index("uq_chat_widgets_public_id", "chat_widgets", ["public_id"], unique=True)

    op.create_index(
        "uq_customers_org_external_id",
        "customers",
        ["organization_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    op.add_column(
        "conversations",
        sa.Column(
            "widget_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("chat_widgets.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_conversations_widget_id", "conversations", ["widget_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_widget_id", table_name="conversations")
    op.drop_column("conversations", "widget_id")
    op.drop_index("uq_customers_org_external_id", table_name="customers")
    op.drop_index("uq_chat_widgets_public_id", table_name="chat_widgets")
    op.drop_index("ix_chat_widgets_org", table_name="chat_widgets")
    op.drop_table("chat_widgets")
    op.execute("DROP TYPE IF EXISTS widget_status")
