from datetime import datetime

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class TeamOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    created_at: datetime
    member_count: int = 0

    model_config = {"from_attributes": True}


class TeamMemberOut(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut] = []


class TeamMemberCreate(BaseModel):
    user_id: str
