from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.auth.permissions import USERS_READ, USERS_WRITE
from app.modules.users.schemas import (
    PasswordReset,
    RoleOut,
    UserCreate,
    UserListItem,
    UserUpdate,
)
from app.modules.users.service import UserService, UserServiceError

router = APIRouter(tags=["users"])


def _raise(exc: UserServiceError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_READ)),
) -> list[RoleOut]:
    return await UserService(db).list_roles()


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_READ)),
) -> list[UserListItem]:
    return await UserService(db).list_users(user.organization_id)


@router.post("/users", response_model=UserListItem, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_WRITE)),
) -> UserListItem:
    try:
        return await UserService(db).create_user(
            user,
            email=str(body.email),
            full_name=body.full_name,
            role_name=body.role,
            password=body.password,
            is_active=body.is_active,
        )
    except UserServiceError as exc:
        _raise(exc)


@router.patch("/users/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_WRITE)),
) -> UserListItem:
    data = body.model_dump(exclude_unset=True)
    try:
        return await UserService(db).update_user(
            user,
            user_id,
            full_name=data.get("full_name"),
            role_name=data.get("role"),
            is_active=data.get("is_active"),
        )
    except UserServiceError as exc:
        _raise(exc)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_password(
    user_id: str,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(USERS_WRITE)),
) -> Response:
    try:
        await UserService(db).reset_password(user, user_id, body.password)
    except UserServiceError as exc:
        _raise(exc)
    return Response(status_code=204)
