from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.ai.application.availability_service import AvailabilityService
from app.modules.auth.permissions import AI_READ, AI_WRITE

router = APIRouter(prefix="/agents", tags=["agents"])


class AvailabilityUpdate(BaseModel):
    is_online: bool


@router.get("/availability")
async def get_agent_availability(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    rows = await AvailabilityService(db).get_availability(user.organization_id)
    return [{"user_id": r.user_id, "is_online": r.is_online, "timezone": r.timezone} for r in rows]


@router.patch("/availability")
async def patch_agent_availability(
    body: AvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    row = await AvailabilityService(db).set_online(user.id, user.organization_id, body.is_online)
    return {"user_id": row.user_id, "is_online": row.is_online}
