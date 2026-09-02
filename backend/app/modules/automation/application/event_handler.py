"""Automation event handler — subscribes to domain events."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.automation.application.execution_service import ExecutionService

logger = logging.getLogger(__name__)

_handler_started = False


async def handle_domain_event(event: DomainEvent) -> None:
    if not event.organization_id:
        return
    depth = int((event.payload or {}).get("execution_depth", 0))
    async with AsyncSessionLocal() as db:
        try:
            await ExecutionService(db).execute_for_event(
                organization_id=event.organization_id,
                event_name=event.name,
                payload=event.payload or {},
                execution_depth=depth,
                trigger_event_id=event.event_id,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Automation handler failed for %s", event.name)


def _wrap_local_handler(message: dict[str, Any]) -> None:
    event = DomainEvent(
        name=message["name"],
        payload=message.get("payload") or {},
        organization_id=message.get("organization_id"),
        event_id=message.get("event_id", ""),
        created_at=message.get("created_at", ""),
    )
    asyncio.create_task(handle_domain_event(event))


async def register_automation_handlers() -> None:
    global _handler_started
    if _handler_started:
        return
    _handler_started = True

    original_publish = event_bus.publish

    async def publish_with_handlers(event: DomainEvent) -> None:
        await original_publish(event)
        if event.organization_id:
            await handle_domain_event(event)

    event_bus.publish = publish_with_handlers  # type: ignore[method-assign]
