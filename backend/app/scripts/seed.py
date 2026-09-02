"""Seed single organization, roles, and default agent user."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.database.models import ChannelConfiguration, ChannelType, Organization, Role, RoleName, Team, TeamMember, User
from app.modules.ai.domain.models import (
    AgentAvailability,
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


def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
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

        agent = session.scalar(select(User).where(User.email == settings.seed_agent_email.lower()))
        if agent is None:
            agent = User(
                organization_id=org.id,
                role_id=roles_by_name[RoleName.AGENT].id,
                email=settings.seed_agent_email.lower(),
                full_name="Demo Agent",
                hashed_password=hash_password(settings.seed_agent_password),
                is_active=True,
            )
            session.add(agent)
            session.flush()

        team = session.scalar(select(Team).where(Team.organization_id == org.id, Team.name == "Support"))
        if team is None:
            team = Team(organization_id=org.id, name="Support", description="Default support team")
            session.add(team)
            session.flush()
            session.add(TeamMember(team_id=team.id, user_id=agent.id))

        billing_team = session.scalar(
            select(Team).where(Team.organization_id == org.id, Team.name == "Billing")
        )
        if billing_team is None:
            billing_team = Team(organization_id=org.id, name="Billing", description="Billing support team")
            session.add(billing_team)
            session.flush()

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
                    restricted_intents=["OTHER"],
                    intent_team_map={
                        "BILLING": "Billing",
                        "REFUND": "Billing",
                        "CANCELLATION": "Billing",
                    },
                )
            )
        else:
            if ai_config.business_hours is None:
                ai_config.business_hours = DEFAULT_BUSINESS_HOURS

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

        availability = session.scalar(select(AgentAvailability).where(AgentAvailability.user_id == agent.id))
        if availability is None:
            session.add(
                AgentAvailability(
                    user_id=agent.id,
                    organization_id=org.id,
                    is_online=True,
                    timezone="UTC",
                    schedule=DEFAULT_BUSINESS_HOURS["schedule"],
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
        print(f"Seeded org={org.id} agent={settings.seed_agent_email}")


if __name__ == "__main__":
    seed()
