from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import Team, User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import TEAMS_READ, TEAMS_WRITE, USERS_READ
from app.modules.teams.schemas import TeamCreate, TeamOut, UserListItem

router = APIRouter(tags=["teams"])


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_READ)),
) -> list[Team]:
    result = await db.execute(select(Team).where(Team.organization_id == user.organization_id).order_by(Team.name))
    return list(result.scalars().all())


@router.post("/teams", response_model=TeamOut, status_code=201)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> Team:
    team = Team(organization_id=user.organization_id, name=body.name, description=body.description)
    db.add(team)
    await db.flush()
    await db.refresh(team)
    return team


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_READ)),
) -> list[User]:
    result = await db.execute(
        select(User).where(User.organization_id == user.organization_id).order_by(User.full_name)
    )
    return list(result.scalars().all())
