from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import TEAMS_READ, TEAMS_WRITE
from app.modules.teams.schemas import (
    TeamCreate,
    TeamDetailOut,
    TeamMemberCreate,
    TeamMemberOut,
    TeamOut,
    TeamUpdate,
)
from app.modules.teams.service import TeamService, TeamServiceError

router = APIRouter(tags=["teams"])


def _raise(exc: TeamServiceError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_READ)),
) -> list[TeamOut]:
    return await TeamService(db).list_teams(user.organization_id)


@router.post("/teams", response_model=TeamOut, status_code=201)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> TeamOut:
    svc = TeamService(db)
    try:
        team = await svc.create_team(user.organization_id, body.name, body.description)
    except TeamServiceError as exc:
        _raise(exc)
    return TeamOut(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=0,
    )


@router.get("/teams/{team_id}", response_model=TeamDetailOut)
async def get_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_READ)),
) -> TeamDetailOut:
    svc = TeamService(db)
    try:
        team = await svc.get_team(user.organization_id, team_id)
        members = await svc.list_members(user.organization_id, team_id)
    except TeamServiceError as exc:
        _raise(exc)
    return TeamDetailOut(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=len(members),
        members=members,
    )


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> TeamOut:
    data = body.model_dump(exclude_unset=True)
    svc = TeamService(db)
    try:
        team = await svc.update_team(
            user.organization_id,
            team_id,
            name=data.get("name"),
            description=data.get("description") if "description" in data else None,
            description_set="description" in data,
        )
        members = await svc.list_members(user.organization_id, team_id)
    except TeamServiceError as exc:
        _raise(exc)
    return TeamOut(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        description=team.description,
        created_at=team.created_at,
        member_count=len(members),
    )


@router.delete("/teams/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> Response:
    try:
        await TeamService(db).delete_team(user.organization_id, team_id)
    except TeamServiceError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberOut])
async def list_team_members(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_READ)),
) -> list[TeamMemberOut]:
    try:
        return await TeamService(db).list_members(user.organization_id, team_id)
    except TeamServiceError as exc:
        _raise(exc)


@router.post("/teams/{team_id}/members", response_model=TeamMemberOut, status_code=201)
async def add_team_member(
    team_id: str,
    body: TeamMemberCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> TeamMemberOut:
    try:
        return await TeamService(db).add_member(user.organization_id, team_id, body.user_id)
    except TeamServiceError as exc:
        _raise(exc)


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    team_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(TEAMS_WRITE)),
) -> Response:
    try:
        await TeamService(db).remove_member(user.organization_id, team_id, user_id)
    except TeamServiceError as exc:
        _raise(exc)
    return Response(status_code=204)
