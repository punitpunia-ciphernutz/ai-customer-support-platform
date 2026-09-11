"""Drop unused AI evaluation suite tables.

Revision ID: 0015_drop_ai_evaluations
Revises: 0014_ai_config_retrieval_mode
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_drop_ai_evaluations"
down_revision: Union[str, None] = "0014_ai_config_retrieval_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_ai_evaluation_results_ai_run_id", table_name="ai_evaluation_results")
    op.drop_index("ix_ai_evaluation_results_evaluation_id", table_name="ai_evaluation_results")
    op.drop_table("ai_evaluation_results")
    op.drop_index("ix_ai_evaluations_organization_id", table_name="ai_evaluations")
    op.drop_table("ai_evaluations")


def downgrade() -> None:
    op.create_table(
        "ai_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_evaluations_organization_id", "ai_evaluations", ["organization_id"])

    op.create_table(
        "ai_evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_evaluations.id"), nullable=False),
        sa.Column("ai_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_runs.id"), nullable=True),
        sa.Column("case_index", sa.Integer(), nullable=False),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("expected", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_evaluation_results_evaluation_id", "ai_evaluation_results", ["evaluation_id"])
    op.create_index("ix_ai_evaluation_results_ai_run_id", "ai_evaluation_results", ["ai_run_id"])
