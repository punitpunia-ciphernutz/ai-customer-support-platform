"""Aggregate AI run cost and token usage for dashboards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Conversation
from app.modules.ai.domain.models import AIRun


class AIUsageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_org_summary(self, organization_id: str, *, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        runs = await self._runs_query(organization_id, since=since)
        return self._summarize(runs, period_days=days)

    async def get_conversation_summary(self, organization_id: str, conversation_id: str) -> dict:
        await self._assert_conversation(organization_id, conversation_id)
        runs = await self._runs_query(organization_id, conversation_id=conversation_id)
        return self._summarize(runs, period_days=None, conversation_id=conversation_id)

    async def _assert_conversation(self, organization_id: str, conversation_id: str) -> None:
        from fastapi import HTTPException

        conv = await self.db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

    async def _runs_query(
        self,
        organization_id: str,
        *,
        since: datetime | None = None,
        conversation_id: str | None = None,
    ) -> list[AIRun]:
        stmt = (
            select(AIRun)
            .join(Conversation, Conversation.id == AIRun.conversation_id)
            .where(Conversation.organization_id == organization_id)
        )
        if conversation_id is not None:
            stmt = stmt.where(AIRun.conversation_id == conversation_id)
        if since is not None:
            stmt = stmt.where(AIRun.created_at >= since)
        stmt = stmt.order_by(AIRun.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def _summarize(
        self,
        runs: list[AIRun],
        *,
        period_days: int | None,
        conversation_id: str | None = None,
    ) -> dict:
        total_cost = 0.0
        input_tokens = 0
        output_tokens = 0
        for run in runs:
            if run.estimated_cost_usd:
                total_cost += float(run.estimated_cost_usd)
            usage = run.token_usage or {}
            input_tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

        return {
            "conversation_id": conversation_id,
            "period_days": period_days,
            "total_runs": len(runs),
            "total_cost_usd": round(total_cost, 6),
            "total_tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
        }

    async def get_org_cost_total(self, organization_id: str) -> float:
        result = await self.db.execute(
            select(func.coalesce(func.sum(AIRun.estimated_cost_usd), 0.0))
            .select_from(AIRun)
            .join(Conversation, Conversation.id == AIRun.conversation_id)
            .where(Conversation.organization_id == organization_id)
        )
        value = result.scalar_one()
        return round(float(value or 0.0), 6)
