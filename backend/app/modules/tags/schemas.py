from datetime import datetime

from pydantic import BaseModel, Field


class TagOut(BaseModel):
    id: str
    organization_id: str
    name: str
    color: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TagNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class TagNamesOut(BaseModel):
    tags: list[str]
