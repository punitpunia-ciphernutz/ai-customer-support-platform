"""Add llm_model to ai_configs for per-org model selection.

Revision ID: 0009_ai_config_llm_model
Revises: 0008_day6_automation
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_ai_config_llm_model"
down_revision: Union[str, None] = "0008_day6_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_configs",
        sa.Column(
            "llm_model",
            sa.String(length=128),
            nullable=False,
            server_default="gemini-3.1-flash-lite",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_configs", "llm_model")
