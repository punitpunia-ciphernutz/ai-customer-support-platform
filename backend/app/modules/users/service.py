"""User administration with RBAC hierarchy guards."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import ActorType, Role, RoleName, TeamMember, User
from app.modules.auth.permissions import can_assign_role, can_manage_user
from app.modules.auth.security import hash_password
from app.modules.users.schemas import RoleBrief, RoleOut, UserListItem, UserTeamBrief


class UserServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_roles(self) -> list[RoleOut]:
        roles = list((await self.db.execute(select(Role).order_by(Role.name))).scalars().all())
        from app.modules.auth.permissions import ROLE_PERMISSIONS

        return [
            RoleOut(name=role.name, permissions=list(ROLE_PERMISSIONS.get(role.name, role.permissions or [])))
            for role in roles
        ]

    async def list_users(self, organization_id: str) -> list[UserListItem]:
        users = list(
            (
                await self.db.execute(
                    select(User)
                    .where(User.organization_id == organization_id)
                    .options(
                        selectinload(User.role),
                        selectinload(User.team_memberships).selectinload(TeamMember.team),
                    )
                    .order_by(User.full_name)
                )
            )
            .scalars()
            .all()
        )
        return [self._to_list_item(user, organization_id) for user in users]

    async def get_user(self, organization_id: str, user_id: str) -> User:
        user = await self.db.scalar(
            select(User)
            .where(User.id == user_id, User.organization_id == organization_id)
            .options(
                selectinload(User.role),
                selectinload(User.team_memberships).selectinload(TeamMember.team),
            )
        )
        if user is None:
            raise UserServiceError(404, "User not found")
        return user

    async def create_user(
        self,
        actor: User,
        *,
        email: str,
        full_name: str,
        role_name: RoleName,
        password: str,
        is_active: bool = True,
    ) -> UserListItem:
        actor_role = self._actor_role(actor)
        if not can_assign_role(actor_role, role_name):
            raise UserServiceError(403, f"Cannot assign role {role_name.value}")

        normalized = email.strip().lower()
        existing = await self.db.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            raise UserServiceError(409, "A user with this email already exists")

        role = await self._get_role(role_name)
        user = User(
            organization_id=actor.organization_id,
            role_id=role.id,
            email=normalized,
            full_name=full_name.strip(),
            hashed_password=hash_password(password),
            is_active=is_active,
        )
        self.db.add(user)
        await self.db.flush()

        await write_audit(
            self.db,
            organization_id=actor.organization_id,
            actor_type=ActorType.USER,
            actor_id=actor.id,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            new_value={"email": user.email, "full_name": user.full_name, "role": role_name.value},
        )
        return UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            role=RoleBrief(id=role.id, name=role.name),
            teams=[],
        )

    async def update_user(
        self,
        actor: User,
        user_id: str,
        *,
        full_name: str | None = None,
        role_name: RoleName | None = None,
        is_active: bool | None = None,
    ) -> UserListItem:
        target = await self.get_user(actor.organization_id, user_id)
        actor_role = self._actor_role(actor)
        target_role = target.role.name if target.role else RoleName.AGENT

        if not can_manage_user(actor_role, target_role):
            raise UserServiceError(403, "Cannot manage a user with equal or higher role")

        old = {
            "full_name": target.full_name,
            "role": target_role.value,
            "is_active": target.is_active,
        }

        if role_name is not None and role_name != target_role:
            if not can_assign_role(actor_role, role_name):
                raise UserServiceError(403, f"Cannot assign role {role_name.value}")
            if target_role == RoleName.OWNER and role_name != RoleName.OWNER:
                await self._ensure_not_last_owner(actor.organization_id, exclude_user_id=target.id)
            role = await self._get_role(role_name)
            target.role_id = role.id
            target.role = role

        if full_name is not None:
            target.full_name = full_name.strip()

        if is_active is not None and is_active != target.is_active:
            if user_id == actor.id and is_active is False:
                raise UserServiceError(409, "Cannot deactivate your own account")
            if target_role == RoleName.OWNER and is_active is False:
                await self._ensure_not_last_owner(actor.organization_id, exclude_user_id=target.id)
            target.is_active = is_active

        await self.db.flush()

        # Re-read role after possible change
        await self.db.refresh(target, attribute_names=["full_name", "is_active", "role_id"])
        new_role_name = role_name.value if role_name is not None else target_role.value
        if target.role is not None:
            new_role_name = target.role.name.value
        new = {
            "full_name": target.full_name,
            "role": new_role_name,
            "is_active": target.is_active,
        }
        action = "user.role_changed" if old["role"] != new["role"] else "user.updated"
        await write_audit(
            self.db,
            organization_id=actor.organization_id,
            actor_type=ActorType.USER,
            actor_id=actor.id,
            action=action,
            entity_type="user",
            entity_id=target.id,
            old_value=old,
            new_value=new,
        )
        return await self.get_user_item(actor.organization_id, target.id)

    async def get_user_item(self, organization_id: str, user_id: str) -> UserListItem:
        user = await self.get_user(organization_id, user_id)
        return self._to_list_item(user, organization_id)

    async def reset_password(self, actor: User, user_id: str, password: str) -> None:
        target = await self.get_user(actor.organization_id, user_id)
        actor_role = self._actor_role(actor)
        target_role = target.role.name if target.role else RoleName.AGENT
        if not can_manage_user(actor_role, target_role):
            raise UserServiceError(403, "Cannot manage a user with equal or higher role")

        target.hashed_password = hash_password(password)
        await self.db.flush()
        await write_audit(
            self.db,
            organization_id=actor.organization_id,
            actor_type=ActorType.USER,
            actor_id=actor.id,
            action="user.password_reset",
            entity_type="user",
            entity_id=target.id,
            new_value={"reset_by": actor.id},
        )

    def _to_list_item(self, user: User, organization_id: str) -> UserListItem:
        teams = [
            UserTeamBrief(id=m.team.id, name=m.team.name)
            for m in (user.team_memberships or [])
            if m.team is not None and m.team.organization_id == organization_id
        ]
        teams.sort(key=lambda t: t.name.lower())
        role = user.role
        if role is None:
            raise UserServiceError(500, "User role not loaded")
        return UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            role=RoleBrief(id=role.id, name=role.name),
            teams=teams,
        )

    async def _get_role(self, role_name: RoleName) -> Role:
        role = await self.db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise UserServiceError(404, f"Role {role_name.value} not found")
        return role

    def _actor_role(self, actor: User) -> RoleName:
        if actor.role is None:
            raise UserServiceError(500, "Actor role not loaded")
        return actor.role.name

    async def _ensure_not_last_owner(self, organization_id: str, *, exclude_user_id: str) -> None:
        count = await self.db.scalar(
            select(func.count())
            .select_from(User)
            .join(Role, Role.id == User.role_id)
            .where(
                User.organization_id == organization_id,
                User.is_active.is_(True),
                Role.name == RoleName.OWNER,
                User.id != exclude_user_id,
            )
        )
        if (count or 0) < 1:
            raise UserServiceError(409, "Cannot remove or deactivate the last active owner")
