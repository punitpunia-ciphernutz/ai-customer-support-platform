from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = None
    company_name: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company_name: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] | None = None


class CustomerOut(BaseModel):
    id: str
    organization_id: str
    name: str
    email: str | None
    phone: str | None
    company_name: str | None
    external_id: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
