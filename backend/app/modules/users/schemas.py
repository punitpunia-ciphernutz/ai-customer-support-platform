from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.infrastructure.database.models import RoleName


class RoleBrief(BaseModel):
    id: str
    name: RoleName


class RoleOut(BaseModel):
    name: RoleName
    permissions: list[str]


class UserTeamBrief(BaseModel):
    id: str
    name: str


class UserListItem(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    role: RoleBrief
    teams: list[UserTeamBrief] = []

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: RoleName
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: RoleName | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)
