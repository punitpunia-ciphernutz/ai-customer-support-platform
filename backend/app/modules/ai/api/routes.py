from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.domain.schemas import ClassifyRequest, ClassifyResponse
from app.modules.auth.permissions import CONVERSATIONS_READ

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/classify", response_model=ClassifyResponse)
async def classify_message(
    body: ClassifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CONVERSATIONS_READ)),
) -> ClassifyResponse:
    classification, run = await AIService(db).classify(
        body.message,
        conversation_id=body.conversation_id,
        message_id=body.message_id,
        context=body.context,
    )
    return ClassifyResponse(classification=classification, ai_run_id=run.id)
