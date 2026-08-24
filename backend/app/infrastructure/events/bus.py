from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import redis.asyncio as redis

from app.config import get_settings


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

    async def publish(self, event: DomainEvent) -> None:
        await self.connect()
        if self._redis is None:
            return
        import json

        await self._redis.publish(self.CHANNEL, json.dumps(asdict(event)))


event_bus = EventBus()
