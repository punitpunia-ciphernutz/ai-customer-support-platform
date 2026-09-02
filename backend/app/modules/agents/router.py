from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.ai.application.availability_service import AvailabilityService
from app.modules.ai.domain.models import AgentStatus
from app.modules.auth.permissions import AI_READ, AI_WRITE

router = APIRouter(prefix="/agents", tags=["agents"])


class AvailabilityUpdate(BaseModel):
    is_online: bool | None = None
    status: AgentStatus | None = None


@router.get("/availability")
async def get_agent_availability(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    rows = await AvailabilityService(db).get_availability(user.organization_id)
    return [
        {
            "user_id": r.user_id,
            "is_online": r.is_online,
            "status": r.status.value if hasattr(r.status, "value") else r.status,
            "active_conversation_count": r.active_conversation_count,
            "last_seen_at": r.last_seen_at,
            "timezone": r.timezone,
        }
        for r in rows
    ]


@router.patch("/availability")
async def patch_agent_availability(
    body: AvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    service = AvailabilityService(db)
    if body.status is not None:
        row = await service.set_status(user.id, user.organization_id, body.status)
    elif body.is_online is not None:
        row = await service.set_online(user.id, user.organization_id, body.is_online)
    else:
        row = await service.set_status(user.id, user.organization_id, AgentStatus.ONLINE)
    await db.commit()
    return {
        "user_id": row.user_id,
        "is_online": row.is_online,
        "status": row.status.value,
        "active_conversation_count": row.active_conversation_count,
    }


@router.patch("/me/availability")
async def patch_my_availability(
    body: AvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
):
    return await patch_agent_availability(body, db, user)
