"""Add Response Policy columns to ai_configs.

Revision ID: 0010_response_policy
Revises: 0009_ai_config_llm_model
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_response_policy"
down_revision: Union[str, None] = "0009_ai_config_llm_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_SCOPE = (
    "password resets, account access, billing questions, and other topics in our help center"
)


def upgrade() -> None:
    op.add_column(
        "ai_configs",
        sa.Column(
            "response_policy_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "soft_reply_greetings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "ood_soft_refuse",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "ood_escalates",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "safe_reply_min_kind_confidence",
            sa.Float(),
            nullable=False,
            server_default="0.55",
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "assistant_scope_summary",
            sa.String(length=1000),
            nullable=False,
            server_default=_DEFAULT_SCOPE,
        ),
    )
    op.add_column(
        "ai_configs",
        sa.Column(
            "assistant_display_name",
            sa.String(length=128),
            nullable=False,
            server_default="Support Assistant",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_configs", "assistant_display_name")
    op.drop_column("ai_configs", "assistant_scope_summary")
    op.drop_column("ai_configs", "safe_reply_min_kind_confidence")
    op.drop_column("ai_configs", "ood_escalates")
    op.drop_column("ai_configs", "ood_soft_refuse")
    op.drop_column("ai_configs", "soft_reply_greetings")
    op.drop_column("ai_configs", "response_policy_enabled")
