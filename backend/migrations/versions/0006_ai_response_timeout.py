"""Add ai_response_timeout_seconds to ai_configs.

Revision ID: 0006_ai_response_timeout
Revises: 0005_day4_ai_reliability
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_ai_response_timeout"
down_revision: Union[str, None] = "0005_day4_ai_reliability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_configs",
        sa.Column("ai_response_timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_column("ai_configs", "ai_response_timeout_seconds")
