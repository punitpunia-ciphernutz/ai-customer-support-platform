"""Day 6 automation, routing, SLA, notifications schema

Revision ID: 0008_day6_automation
Revises: 0007_day5_omnichannel
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_day6_automation"
down_revision: Union[str, None] = "0007_day5_omnichannel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    agent_status = postgresql.ENUM("ONLINE", "AWAY", "OFFLINE", name="agent_status", create_type=True)
    agent_status.create(bind, checkfirst=True)

    automation_execution_status = postgresql.ENUM(
        "RUNNING", "COMPLETED", "FAILED", "SKIPPED", name="automation_execution_status", create_type=True
    )
    automation_execution_status.create(bind, checkfirst=True)

    automation_step_type = postgresql.ENUM("CONDITION", "ACTION", name="automation_step_type", create_type=True)
    automation_step_type.create(bind, checkfirst=True)

    sla_timer_type = postgresql.ENUM("FIRST_RESPONSE", "RESOLUTION", name="sla_timer_type", create_type=True)
    sla_timer_type.create(bind, checkfirst=True)

    sla_timer_status = postgresql.ENUM(
        "RUNNING", "PAUSED", "COMPLETED", "BREACHED", name="sla_timer_status", create_type=True
    )
    sla_timer_status.create(bind, checkfirst=True)

    op.add_column(
        "agent_availability",
        sa.Column(
            "status",
            postgresql.ENUM("ONLINE", "AWAY", "OFFLINE", name="agent_status", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("agent_availability", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_availability",
        sa.Column("active_conversation_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE agent_availability SET status = CASE WHEN is_online THEN 'ONLINE'::agent_status "
        "ELSE 'OFFLINE'::agent_status END"
    )
    op.alter_column("agent_availability", "status", nullable=False)

    op.add_column("teams", sa.Column("last_assigned_user_id", postgresql.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key("fk_teams_last_assigned_user", "teams", "users", ["last_assigned_user_id"], ["id"])

    op.create_table(
        "business_hours",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_business_hours_org", "business_hours", ["organization_id"])

    op.create_table(
        "business_hours_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("business_hours_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("business_hours.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.UniqueConstraint("business_hours_id", "day_of_week", name="uq_business_hours_day"),
    )

    op.create_table(
        "business_holidays",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("business_hours_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("business_hours.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("business_hours_id", "date", name="uq_business_holiday_date"),
    )

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_tag_org_name"),
    )

    op.create_table(
        "conversation_tags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tags.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("conversation_id", "tag_id", name="uq_conversation_tag"),
    )

    op.create_table(
        "ticket_tags",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tags.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("ticket_id", "tag_id", name="uq_ticket_tag"),
    )

    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("trigger", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=True),
        sa.Column("actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_automations_org_enabled_priority", "automations", ["organization_id", "enabled", "priority"])

    op.create_table(
        "automation_executions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("automation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("automations.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("trigger_event", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "RUNNING", "COMPLETED", "FAILED", "SKIPPED",
                name="automation_execution_status",
                create_type=False,
            ),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_index("ix_automation_executions_entity", "automation_executions", ["entity_type", "entity_id"])

    op.create_table(
        "automation_execution_steps",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("execution_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("automation_executions.id"), nullable=False),
        sa.Column(
            "step_type",
            postgresql.ENUM("CONDITION", "ACTION", name="automation_step_type", create_type=False),
            nullable=False,
        ),
        sa.Column("configuration", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "RUNNING", "COMPLETED", "FAILED", "SKIPPED",
                name="automation_execution_status",
                create_type=False,
            ),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("business_hours_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("business_hours.id"), nullable=True),
        sa.Column("applies_to", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sla_timers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("sla_policy_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sla_policies.id"), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=True),
        sa.Column(
            "type",
            postgresql.ENUM("FIRST_RESPONSE", "RESOLUTION", name="sla_timer_type", create_type=False),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("breached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "RUNNING", "PAUSED", "COMPLETED", "BREACHED",
                name="sla_timer_status",
                create_type=False,
            ),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("in_app", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("email", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "event_type", name="uq_notification_pref_user_event"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
    op.drop_table("sla_timers")
    op.drop_table("sla_policies")
    op.drop_table("automation_execution_steps")
    op.drop_table("automation_executions")
    op.drop_table("automations")
    op.drop_table("ticket_tags")
    op.drop_table("conversation_tags")
    op.drop_table("tags")
    op.drop_table("business_holidays")
    op.drop_table("business_hours_schedules")
    op.drop_table("business_hours")
    op.drop_constraint("fk_teams_last_assigned_user", "teams", type_="foreignkey")
    op.drop_column("teams", "last_assigned_user_id")
    op.drop_column("agent_availability", "active_conversation_count")
    op.drop_column("agent_availability", "last_seen_at")
    op.drop_column("agent_availability", "status")
    op.execute("DROP TYPE IF EXISTS sla_timer_status")
    op.execute("DROP TYPE IF EXISTS sla_timer_type")
    op.execute("DROP TYPE IF EXISTS automation_step_type")
    op.execute("DROP TYPE IF EXISTS automation_execution_status")
    op.execute("DROP TYPE IF EXISTS agent_status")
