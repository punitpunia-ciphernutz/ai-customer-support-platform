"""Seed single organization, roles, and default agent user."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.database.models import Organization, Role, RoleName, Team, TeamMember, User
from app.modules.auth.permissions import ROLE_PERMISSIONS
from app.modules.auth.security import hash_password


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

        session.commit()
        print(f"Seeded org={org.id} agent={settings.seed_agent_email}")


if __name__ == "__main__":
    seed()
