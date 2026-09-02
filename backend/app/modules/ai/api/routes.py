from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_db
from app.modules.ai.application.ai_config_service import get_or_create_ai_config, update_ai_config
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.application.evaluation_service import EvaluationService
from app.modules.ai.domain.models import AI_MODE_DISPLAY, AIRun, BotConfiguration
from app.modules.ai.domain.schemas import (
    AIConfigOut,
    AIConfigUpdate,
    AIRunDetail,
    AIRunSummary,
    AITestRequest,
    AITestResponse,
    BotConfigurationOut,
    ClassifyRequest,
    ClassifyResponse,
    EvaluationReport,
)
from app.modules.auth.permissions import AI_READ, AI_WRITE, CONVERSATIONS_READ

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


@router.post("/test", response_model=AITestResponse)
async def test_ai_agent(
    body: AITestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
) -> AITestResponse:
    org_id = body.organization_id or user.organization_id
    response = await AIService(db).run_test(
        body.message,
        organization_id=org_id,
        conversation_id=body.conversation_id,
    )
    return AITestResponse(
        intent=response.intent,
        confidence=response.confidence,
        grounded=response.grounded,
        answer=response.answer,
        sources=response.citations,
        escalation_required=response.escalation_required,
        escalation_reason=response.escalation_reason,
        decision=response.decision,
    )


@router.get("/runs", response_model=list[AIRunSummary])
async def list_ai_runs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AIRun]:
    from app.infrastructure.database.models import Conversation

    conv_result = await db.execute(
        select(AIRun)
        .join(Conversation, Conversation.id == AIRun.conversation_id)
        .where(Conversation.organization_id == user.organization_id)
        .order_by(AIRun.created_at.desc())
        .limit(limit)
    )
    return list(conv_result.scalars().all())


@router.get("/runs/{run_id}", response_model=AIRunDetail)
async def get_ai_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
) -> AIRun:
    from app.infrastructure.database.models import Conversation

    result = await db.execute(
        select(AIRun)
        .join(Conversation, Conversation.id == AIRun.conversation_id)
        .where(AIRun.id == run_id, Conversation.organization_id == user.organization_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        # Allow test runs without conversation
        run = await db.get(AIRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="AI run not found")
    return run


async def _config_out(db: AsyncSession, organization_id: str) -> AIConfigOut:
    config = await get_or_create_ai_config(db, organization_id)
    overrides = await db.execute(
        select(BotConfiguration).where(BotConfiguration.organization_id == organization_id)
    )
    out = AIConfigOut.model_validate(config)
    out.mode_display = AI_MODE_DISPLAY.get(config.mode, config.mode.value)
    out.channel_overrides = [BotConfigurationOut.model_validate(o) for o in overrides.scalars().all()]
    return out


@router.get("/config", response_model=AIConfigOut)
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
) -> AIConfigOut:
    return await _config_out(db, user.organization_id)


@router.patch("/config", response_model=AIConfigOut)
async def patch_ai_config(
    body: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
) -> AIConfigOut:
    await update_ai_config(db, user.organization_id, body)
    return await _config_out(db, user.organization_id)


@router.get("/evaluations")
async def list_evaluations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_READ)),
):
    ev = await EvaluationService(db).get_or_create_evaluation(user.organization_id)
    return {"id": ev.id, "name": ev.name, "case_count": ev.case_count, "version": ev.version}


@router.post("/evaluations/run", response_model=EvaluationReport)
async def run_evaluations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(AI_WRITE)),
) -> EvaluationReport:
    report = await EvaluationService(db).run_suite(user.organization_id)
    await db.commit()
    return report
