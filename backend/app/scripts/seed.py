"""Seed organization, roles, demo users, teams, and Day 6 defaults."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.database.models import (
    ChannelConfiguration,
    ChannelType,
    Conversation,
    Organization,
    Role,
    RoleName,
    Team,
    TeamMember,
    Ticket,
    User,
)
from app.modules.ai.domain.models import (
    AgentAvailability,
    AgentStatus,
    AIEvaluation,
    AIConfig,
    AIMode,
    BotConfiguration,
    Prompt,
    PromptVersion,
)
from app.modules.ai.prompts.seed_templates import (
    DEFAULT_BUSINESS_HOURS,
    GROUNDING_VALIDATOR_TEMPLATE,
    SUPPORT_AGENT_SYSTEM_TEMPLATE,
)
from app.modules.auth.permissions import ROLE_PERMISSIONS
from app.modules.auth.security import hash_password
from app.modules.automation.domain.models import Automation
from app.modules.notifications.application.service import DEFAULT_EVENT_TYPES
from app.modules.notifications.domain.models import Notification, NotificationPreference


@dataclass(frozen=True)
class DemoUserSpec:
    email: str
    full_name: str
    role: RoleName
    teams: tuple[str, ...] = ()
    password: str | None = None  # defaults to SEED_AGENT_PASSWORD
    online: bool = False


# Canonical demo roster — reseed keeps these; junk test users are removed.
DEMO_USERS: tuple[DemoUserSpec, ...] = (
    DemoUserSpec("owner@example.com", "Ava Owner", RoleName.OWNER),
    DemoUserSpec("admin@example.com", "Noah Admin", RoleName.ADMIN),
    DemoUserSpec("manager@example.com", "Maya Manager", RoleName.MANAGER, teams=("Support",)),
    DemoUserSpec(
        "agent@example.com",
        "Alex Agent",
        RoleName.AGENT,
        teams=("Support", "Billing"),
        online=True,
    ),
    DemoUserSpec(
        "priya.support@example.com",
        "Priya Shah",
        RoleName.AGENT,
        teams=("Support",),
        online=True,
    ),
    DemoUserSpec(
        "jordan.billing@example.com",
        "Jordan Lee",
        RoleName.AGENT,
        teams=("Billing",),
        online=True,
    ),
    DemoUserSpec(
        "sam.both@example.com",
        "Sam Rivera",
        RoleName.AGENT,
        teams=("Support", "Billing"),
        online=True,
    ),
    DemoUserSpec("readonly@example.com", "Riley Reader", RoleName.READ_ONLY),
)

DEMO_TEAMS: tuple[tuple[str, str], ...] = (
    ("Support", "Default support team"),
    ("Billing", "Billing support team"),
)


def _seed_prompts(session: Session) -> None:
    prompts = [
        ("support_agent_system", "Support agent generation prompt", SUPPORT_AGENT_SYSTEM_TEMPLATE),
        ("grounding_validator", "Post-generation grounding check", GROUNDING_VALIDATOR_TEMPLATE),
    ]
    for name, description, template in prompts:
        prompt = session.scalar(select(Prompt).where(Prompt.name == name))
        if prompt is None:
            prompt = Prompt(name=name, description=description)
            session.add(prompt)
            session.flush()
        existing = session.scalar(
            select(PromptVersion).where(PromptVersion.prompt_id == prompt.id, PromptVersion.version == 1)
        )
        if existing is None:
            session.add(
                PromptVersion(
                    prompt_id=prompt.id,
                    version=1,
                    template=template,
                    active=True,
                    configuration={},
                )
            )


def _delete_users(session: Session, user_ids: list[str]) -> None:
    if not user_ids:
        return
    session.execute(update(Team).where(Team.last_assigned_user_id.in_(user_ids)).values(last_assigned_user_id=None))
    session.execute(
        update(Conversation).where(Conversation.assigned_user_id.in_(user_ids)).values(assigned_user_id=None)
    )
    session.execute(update(Ticket).where(Ticket.assigned_user_id.in_(user_ids)).values(assigned_user_id=None))
    session.execute(update(Automation).where(Automation.created_by.in_(user_ids)).values(created_by=None))
    session.execute(delete(TeamMember).where(TeamMember.user_id.in_(user_ids)))
    session.execute(delete(AgentAvailability).where(AgentAvailability.user_id.in_(user_ids)))
    session.execute(delete(NotificationPreference).where(NotificationPreference.user_id.in_(user_ids)))
    session.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
    session.execute(delete(User).where(User.id.in_(user_ids)))
    session.flush()


def _cleanup_junk_users(session: Session, org_id: str, keep_emails: set[str]) -> int:
    """Remove users not in the demo roster (e.g. readonly-<uuid>@example.com from pytest)."""
    junk = list(
        session.scalars(
            select(User).where(
                User.organization_id == org_id,
                User.email.notin_(keep_emails),
            )
        ).all()
    )
    to_delete = [u.id for u in junk]
    _delete_users(session, to_delete)
    return len(to_delete)


def _ensure_team(session: Session, org_id: str, name: str, description: str) -> Team:
    team = session.scalar(select(Team).where(Team.organization_id == org_id, Team.name == name))
    if team is None:
        team = Team(organization_id=org_id, name=name, description=description)
        session.add(team)
        session.flush()
    else:
        team.description = description
    return team


def _ensure_membership(session: Session, team_id: str, user_id: str) -> None:
    existing = session.scalar(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    if existing is None:
        session.add(TeamMember(team_id=team_id, user_id=user_id))


def _ensure_availability(session: Session, org_id: str, user_id: str, *, online: bool) -> None:
    availability = session.scalar(select(AgentAvailability).where(AgentAvailability.user_id == user_id))
    status = AgentStatus.ONLINE if online else AgentStatus.OFFLINE
    if availability is None:
        session.add(
            AgentAvailability(
                user_id=user_id,
                organization_id=org_id,
                is_online=online,
                status=status,
                timezone="UTC",
                schedule=DEFAULT_BUSINESS_HOURS["schedule"],
            )
        )
    else:
        availability.is_online = online
        availability.status = status


def _ensure_notification_prefs(session: Session, user_id: str) -> None:
    for event_type in DEFAULT_EVENT_TYPES:
        existing = session.scalar(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.event_type == event_type,
            )
        )
        if existing is None:
            session.add(
                NotificationPreference(
                    user_id=user_id,
                    event_type=event_type,
                    in_app=True,
                    email=False,
                    enabled=True,
                )
            )


def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    default_password = settings.seed_agent_password
    keep_emails = {u.email.lower() for u in DEMO_USERS}
    # Always keep configured seed agent email (may match agent@example.com).
    keep_emails.add(settings.seed_agent_email.lower())

    with Session(engine) as session:
        org = session.scalar(select(Organization).limit(1))
        if org is None:
            org = Organization(
                name="Acme Support",
                domain="acme.example",
                timezone="UTC",
                settings={},
            )
            session.add(org)
            session.flush()

        roles_by_name: dict[RoleName, Role] = {}
        for role_name, perms in ROLE_PERMISSIONS.items():
            role = session.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                role = Role(name=role_name, permissions=perms)
                session.add(role)
                session.flush()
            else:
                role.permissions = perms
            roles_by_name[role_name] = role

        removed = _cleanup_junk_users(session, org.id, keep_emails)

        teams_by_name = {
            name: _ensure_team(session, org.id, name, description) for name, description in DEMO_TEAMS
        }

        users_by_email: dict[str, User] = {}
        for spec in DEMO_USERS:
            email = spec.email.lower()
            # Prefer configured seed agent email for the primary agent slot.
            if spec.email == "agent@example.com":
                email = settings.seed_agent_email.lower()
            password = spec.password or default_password
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    organization_id=org.id,
                    role_id=roles_by_name[spec.role].id,
                    email=email,
                    full_name=spec.full_name,
                    hashed_password=hash_password(password),
                    is_active=True,
                )
                session.add(user)
                session.flush()
            else:
                user.full_name = spec.full_name
                user.role_id = roles_by_name[spec.role].id
                user.hashed_password = hash_password(password)
                user.is_active = True
            users_by_email[email] = user

            # Reset memberships for this user to the demo roster only.
            session.execute(delete(TeamMember).where(TeamMember.user_id == user.id))
            for team_name in spec.teams:
                _ensure_membership(session, teams_by_name[team_name].id, user.id)

            if spec.role == RoleName.AGENT:
                _ensure_availability(session, org.id, user.id, online=spec.online)
            _ensure_notification_prefs(session, user.id)

        ai_config = session.scalar(select(AIConfig).where(AIConfig.organization_id == org.id))
        if ai_config is None:
            session.add(
                AIConfig(
                    organization_id=org.id,
                    enabled=True,
                    mode=AIMode.AUTO_REPLY,
                    auto_reply_threshold=0.85,
                    escalation_threshold=0.85,
                    min_relevance_score=0.35,
                    require_knowledge=True,
                    escalate_if_unknown=True,
                    multilingual_enabled=True,
                    hybrid_keyword_weight=0.3,
                    business_hours=DEFAULT_BUSINESS_HOURS,
                    missed_chat_timeout_minutes=5,
                    llm_model="gemini-3.1-flash-lite",
                    restricted_intents=["OTHER"],
                    intent_team_map={},
                    response_policy_enabled=True,
                    soft_reply_greetings=True,
                    ood_soft_refuse=True,
                    ood_escalates=False,
                    safe_reply_min_kind_confidence=0.55,
                    assistant_scope_summary=(
                        "password resets, account access, billing questions, "
                        "and other topics in our help center"
                    ),
                    assistant_display_name="Support Assistant",
                )
            )
        else:
            if ai_config.business_hours is None:
                ai_config.business_hours = DEFAULT_BUSINESS_HOURS
            ai_config.intent_team_map = {}

        for channel, mode in [
            (ChannelType.WEB_CHAT.value, AIMode.AUTO_REPLY),
            (ChannelType.EMAIL.value, AIMode.SUGGEST),
            (ChannelType.FORM.value, AIMode.DRAFT_ONLY),
        ]:
            bot_cfg = session.scalar(
                select(BotConfiguration).where(
                    BotConfiguration.organization_id == org.id,
                    BotConfiguration.channel == channel,
                )
            )
            if bot_cfg is None:
                session.add(
                    BotConfiguration(
                        organization_id=org.id,
                        channel=channel,
                        mode=mode,
                    )
                )

        _seed_prompts(session)

        evaluation = session.scalar(
            select(AIEvaluation).where(
                AIEvaluation.organization_id == org.id,
                AIEvaluation.name == "Day 4 Baseline",
            )
        )
        from app.modules.ai.application.evaluation_service import EVALUATION_CASES

        if evaluation is None:
            session.add(
                AIEvaluation(
                    organization_id=org.id,
                    name="Day 4 Baseline",
                    version=1,
                    case_count=len(EVALUATION_CASES),
                    cases=EVALUATION_CASES,
                )
            )
        else:
            evaluation.case_count = len(EVALUATION_CASES)
            evaluation.cases = EVALUATION_CASES

        for channel in ChannelType:
            ch_cfg = session.scalar(
                select(ChannelConfiguration).where(
                    ChannelConfiguration.organization_id == org.id,
                    ChannelConfiguration.channel == channel,
                )
            )
            if ch_cfg is None:
                session.add(
                    ChannelConfiguration(
                        organization_id=org.id,
                        channel=channel,
                        enabled=channel in (ChannelType.WEB_CHAT, ChannelType.EMAIL),
                        provider="mock" if channel == ChannelType.EMAIL else None,
                        settings={"from_address": "support@acme.example"} if channel == ChannelType.EMAIL else {},
                    )
                )

        session.commit()
        agent_email = settings.seed_agent_email.lower()
        print(
            f"Seeded org={org.id} users={len(users_by_email)} "
            f"removed_junk={removed} primary_agent={agent_email}"
        )

        from app.scripts.seed_day6 import seed_business_hours, seed_default_automations, seed_sla_policies

        bh = seed_business_hours(session, org.id, org.timezone or "UTC")
        seed_sla_policies(session, org.id, bh.id)
        seed_default_automations(session, org.id)
        session.commit()


if __name__ == "__main__":
    seed()
