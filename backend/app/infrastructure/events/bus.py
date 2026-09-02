import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

EventHandler = Callable[["DomainEvent"], Awaitable[None]]


@dataclass
class DomainEvent:
    name: str
    payload: dict[str, Any]
    organization_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class EventBus:
    """In-process + Redis pub/sub bridge for realtime fan-out."""

    CHANNEL = "support.events"

    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._handlers: list[EventHandler] = []

    async def connect(self) -> None:
        if self._redis is None:
            try:
                client = redis.from_url(get_settings().redis_url, decode_responses=True)
                await client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    def subscribe(self, handler: EventHandler) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)

    async def publish(self, event: DomainEvent) -> None:
        await self.connect()
        if self._redis is not None:
            import json

            await self._redis.publish(self.CHANNEL, json.dumps(asdict(event)))

        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("Event handler failed for %s", event.name)


event_bus = EventBus()
