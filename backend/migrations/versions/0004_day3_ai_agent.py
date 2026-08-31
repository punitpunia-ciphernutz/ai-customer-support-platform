"""Day 3 AI agent: extend ai_runs, add ai_configs

Revision ID: 0004_day3_ai_agent
Revises: 0003_ai_runs
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_day3_ai_agent"
down_revision: Union[str, None] = "0003_ai_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("ALTER TYPE ai_run_type ADD VALUE IF NOT EXISTS 'AGENT'")
    op.execute("ALTER TYPE ai_run_status ADD VALUE IF NOT EXISTS 'COMPLETED'")

    op.add_column("ai_runs", sa.Column("graph_version", sa.String(64), nullable=True))
    op.add_column("ai_runs", sa.Column("intent", sa.String(64), nullable=True))
    op.add_column("ai_runs", sa.Column("retrieval_count", sa.Integer(), nullable=True))
    op.add_column("ai_runs", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("ai_runs", sa.Column("processing_key", sa.String(128), nullable=True))
    op.create_index("ix_ai_runs_processing_key", "ai_runs", ["processing_key"], unique=False)
    op.create_unique_constraint("uq_ai_runs_processing_key", "ai_runs", ["processing_key"])

    ai_mode = postgresql.ENUM("DRAFT_ONLY", "SUGGEST", "AUTO_REPLY", name="ai_mode", create_type=False)
    ai_mode.create(bind, checkfirst=True)

    op.create_table(
        "ai_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mode", ai_mode, nullable=False, server_default="AUTO_REPLY"),
        sa.Column("auto_reply_threshold", sa.Float(), nullable=False, server_default="0.85"),
        sa.Column("escalation_threshold", sa.Float(), nullable=False, server_default="0.85"),
        sa.Column("allowed_intents", postgresql.JSONB()),
        sa.Column("restricted_intents", postgresql.JSONB(), server_default=sa.text("'[\"OTHER\"]'::jsonb")),
        sa.Column("intent_team_map", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_configs_organization_id", "ai_configs", ["organization_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ai_configs_organization_id", table_name="ai_configs")
    op.drop_table("ai_configs")
    op.drop_constraint("uq_ai_runs_processing_key", "ai_runs", type_="unique")
    op.drop_index("ix_ai_runs_processing_key", table_name="ai_runs")
    op.drop_column("ai_runs", "processing_key")
    op.drop_column("ai_runs", "confidence")
    op.drop_column("ai_runs", "retrieval_count")
    op.drop_column("ai_runs", "intent")
    op.drop_column("ai_runs", "graph_version")
    bind = op.get_bind()
    sa.Enum(name="ai_mode").drop(bind, checkfirst=True)
