from datetime import datetime

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TeamOut(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListItem(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool

    model_config = {"from_attributes": True}
