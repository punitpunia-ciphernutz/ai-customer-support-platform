"""Day 4 AI reliability: prompts, evaluation, extended ai_runs, conversation control

Revision ID: 0005_day4_ai_reliability
Revises: 0004_day3_ai_agent
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_day4_ai_reliability"
down_revision: Union[str, None] = "0004_day3_ai_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("ALTER TYPE ai_run_type ADD VALUE IF NOT EXISTS 'EVALUATION'")
    op.execute("ALTER TYPE conversation_status ADD VALUE IF NOT EXISTS 'WAITING_FOR_AGENT'")

    ai_control_mode = postgresql.ENUM("AI_CONTROL", "HUMAN_CONTROL", name="ai_control_mode", create_type=False)
    ai_control_mode.create(bind, checkfirst=True)

    ticket_source = postgresql.ENUM(
        "AI_ESCALATION",
        "MISSED_CHAT",
        "AGENT_CREATED",
        "HELP_CENTER",
        "AUTOMATION",
        name="ticket_source",
        create_type=False,
    )
    ticket_source.create(bind, checkfirst=True)

    op.add_column(
        "conversations",
        sa.Column("ai_control_mode", ai_control_mode, nullable=False, server_default="AI_CONTROL"),
    )
    op.add_column("conversations", sa.Column("conversation_summary", sa.Text(), nullable=True))

    op.add_column("tickets", sa.Column("customer_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column("tickets", sa.Column("source", ticket_source, nullable=False, server_default="AGENT_CREATED"))
    op.add_column("tickets", sa.Column("title", sa.String(512), nullable=True))
    op.add_column("tickets", sa.Column("description", sa.Text(), nullable=True))
    op.create_foreign_key("fk_tickets_customer_id", "tickets", "customers", ["customer_id"], ["id"])
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"])

    # Extend ai_runs
    op.add_column("ai_runs", sa.Column("prompt_version", sa.String(128), nullable=True))
    op.add_column("ai_runs", sa.Column("retrieval_score", sa.Float(), nullable=True))
    op.add_column("ai_runs", sa.Column("grounding_score", sa.Float(), nullable=True))
    op.add_column("ai_runs", sa.Column("confidence_components", postgresql.JSONB(), nullable=True))
    op.add_column("ai_runs", sa.Column("decision", sa.String(32), nullable=True))
    op.add_column("ai_runs", sa.Column("language", sa.String(16), nullable=True))
    op.add_column("ai_runs", sa.Column("sentiment", sa.String(32), nullable=True))
    op.add_column("ai_runs", sa.Column("estimated_cost_usd", sa.Float(), nullable=True))
    op.add_column("ai_runs", sa.Column("trace", postgresql.JSONB(), nullable=True))

    # Extend ai_configs
    op.add_column("ai_configs", sa.Column("min_relevance_score", sa.Float(), nullable=False, server_default="0.35"))
    op.add_column("ai_configs", sa.Column("require_knowledge", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("ai_configs", sa.Column("escalate_if_unknown", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("ai_configs", sa.Column("multilingual_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("ai_configs", sa.Column("hybrid_keyword_weight", sa.Float(), nullable=False, server_default="0.3"))
    op.add_column("ai_configs", sa.Column("business_hours", postgresql.JSONB(), nullable=True))
    op.add_column("ai_configs", sa.Column("missed_chat_timeout_minutes", sa.Integer(), nullable=False, server_default="5"))

    ai_mode = postgresql.ENUM("DRAFT_ONLY", "SUGGEST", "AUTO_REPLY", name="ai_mode", create_type=False)

    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_prompts_name", "prompts", ["name"], unique=True)

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("prompts.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
    )
    op.create_index("ix_prompt_versions_prompt_id", "prompt_versions", ["prompt_id"])

    op.create_table(
        "bot_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("mode", ai_mode),
        sa.Column("auto_reply_threshold", sa.Float()),
        sa.Column("escalation_threshold", sa.Float()),
        sa.Column("min_relevance_score", sa.Float()),
        sa.Column("require_knowledge", sa.Boolean()),
        sa.Column("multilingual_enabled", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "channel", name="uq_bot_config_org_channel"),
    )
    op.create_index("ix_bot_configurations_organization_id", "bot_configurations", ["organization_id"])

    op.create_table(
        "ai_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cases", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_evaluations_organization_id", "ai_evaluations", ["organization_id"])

    op.create_table(
        "ai_evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_evaluations.id"), nullable=False),
        sa.Column("ai_run_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_runs.id")),
        sa.Column("case_index", sa.Integer(), nullable=False),
        sa.Column("input_message", sa.Text(), nullable=False),
        sa.Column("expected", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scores", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_evaluation_results_evaluation_id", "ai_evaluation_results", ["evaluation_id"])
    op.create_index("ix_ai_evaluation_results_ai_run_id", "ai_evaluation_results", ["ai_run_id"])

    op.create_table(
        "agent_availability",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("schedule", postgresql.JSONB()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_agent_availability_user"),
    )
    op.create_index("ix_agent_availability_user_id", "agent_availability", ["user_id"])
    op.create_index("ix_agent_availability_organization_id", "agent_availability", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_availability_organization_id", table_name="agent_availability")
    op.drop_index("ix_agent_availability_user_id", table_name="agent_availability")
    op.drop_table("agent_availability")

    op.drop_index("ix_ai_evaluation_results_ai_run_id", table_name="ai_evaluation_results")
    op.drop_index("ix_ai_evaluation_results_evaluation_id", table_name="ai_evaluation_results")
    op.drop_table("ai_evaluation_results")

    op.drop_index("ix_ai_evaluations_organization_id", table_name="ai_evaluations")
    op.drop_table("ai_evaluations")

    op.drop_index("ix_bot_configurations_organization_id", table_name="bot_configurations")
    op.drop_table("bot_configurations")

    op.drop_index("ix_prompt_versions_prompt_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")

    op.drop_index("ix_prompts_name", table_name="prompts")
    op.drop_table("prompts")

    op.drop_column("ai_configs", "missed_chat_timeout_minutes")
    op.drop_column("ai_configs", "business_hours")
    op.drop_column("ai_configs", "hybrid_keyword_weight")
    op.drop_column("ai_configs", "multilingual_enabled")
    op.drop_column("ai_configs", "escalate_if_unknown")
    op.drop_column("ai_configs", "require_knowledge")
    op.drop_column("ai_configs", "min_relevance_score")

    op.drop_column("ai_runs", "trace")
    op.drop_column("ai_runs", "estimated_cost_usd")
    op.drop_column("ai_runs", "sentiment")
    op.drop_column("ai_runs", "language")
    op.drop_column("ai_runs", "decision")
    op.drop_column("ai_runs", "confidence_components")
    op.drop_column("ai_runs", "grounding_score")
    op.drop_column("ai_runs", "retrieval_score")
    op.drop_column("ai_runs", "prompt_version")

    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_constraint("fk_tickets_customer_id", "tickets", type_="foreignkey")
    op.drop_column("tickets", "description")
    op.drop_column("tickets", "title")
    op.drop_column("tickets", "source")
    op.drop_column("tickets", "customer_id")

    op.drop_column("conversations", "conversation_summary")
    op.drop_column("conversations", "ai_control_mode")

    bind = op.get_bind()
    sa.Enum(name="ticket_source").drop(bind, checkfirst=True)
    sa.Enum(name="ai_control_mode").drop(bind, checkfirst=True)
