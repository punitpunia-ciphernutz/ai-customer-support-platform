from datetime import datetime

from pydantic import BaseModel

from app.infrastructure.database.models import Priority, TicketStatus


class TicketCreate(BaseModel):
    conversation_id: str
    priority: Priority = Priority.NORMAL
    assigned_user_id: str | None = None
    assigned_team_id: str | None = None


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    priority: Priority | None = None
    assigned_user_id: str | None = None
    assigned_team_id: str | None = None


class TicketOut(BaseModel):
    id: str
    organization_id: str
    conversation_id: str
    status: TicketStatus
    priority: Priority
    assigned_user_id: str | None
    assigned_team_id: str | None
    created_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None

    model_config = {"from_attributes": True}
