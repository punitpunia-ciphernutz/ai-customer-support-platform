"""Add optional AIConfig.retrieval_mode for hybrid search canary/rollback.

Revision ID: 0014_ai_config_retrieval_mode
Revises: 0013_document_chunks_fts
Create Date: 2026-09-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_ai_config_retrieval_mode"
down_revision: Union[str, None] = "0013_document_chunks_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_configs",
        sa.Column(
            "retrieval_mode",
            sa.String(32),
            nullable=True,
            comment="null = use AI_RETRIEVAL_MODE env default; legacy | hybrid_rrf",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_configs", "retrieval_mode")
