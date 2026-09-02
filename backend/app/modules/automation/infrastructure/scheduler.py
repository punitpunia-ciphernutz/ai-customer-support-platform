"""Celery scheduling for automation-related delayed jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def schedule_missed_chat_check(conversation_id: str, organization_id: str, delay_minutes: int) -> None:
    from app.workers.tasks import check_missed_chat

    eta = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    check_missed_chat.apply_async(args=[conversation_id, organization_id], eta=eta)
