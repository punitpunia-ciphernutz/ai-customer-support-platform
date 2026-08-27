"""ai_runs table

Revision ID: 0003_ai_runs
Revises: 0002_knowledge
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ai_runs"
down_revision: Union[str, None] = "0002_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    ai_run_type = _enum(
        "CLASSIFICATION", "GENERATION", "SUMMARY", "RETRIEVAL", name="ai_run_type"
    )
    ai_run_status = _enum("PENDING", "RUNNING", "SUCCEEDED", "FAILED", name="ai_run_status")
    bind = op.get_bind()
    ai_run_type.create(bind, checkfirst=True)
    ai_run_status.create(bind, checkfirst=True)

    op.create_table(
        "ai_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("conversations.id")),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("messages.id")),
        sa.Column("type", ai_run_type, nullable=False),
        sa.Column("status", ai_run_status, nullable=False, server_default="PENDING"),
        sa.Column("model", sa.String(128)),
        sa.Column("input", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output", postgresql.JSONB()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("token_usage", postgresql.JSONB()),
        sa.Column("error", sa.String(2000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_runs_conversation_id", "ai_runs", ["conversation_id"])
    op.create_index("ix_ai_runs_message_id", "ai_runs", ["message_id"])


def downgrade() -> None:
    op.drop_table("ai_runs")
    bind = op.get_bind()
    sa.Enum(name="ai_run_status").drop(bind, checkfirst=True)
    sa.Enum(name="ai_run_type").drop(bind, checkfirst=True)
