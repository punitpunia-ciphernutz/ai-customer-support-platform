from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleOut(BaseModel):
    id: str
    name: str
    permissions: list[str]

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    organization_id: str
    email: EmailStr
    full_name: str
    is_active: bool
    role: RoleOut
    created_at: datetime

    model_config = {"from_attributes": True}
