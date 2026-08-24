import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.infrastructure.events.bus import EventBus
from app.modules.auth.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
_listener_task: asyncio.Task | None = None


async def _redis_listener() -> None:
    import redis.asyncio as redis

    while True:
        client = None
        pubsub = None
        try:
            client = redis.from_url(get_settings().redis_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(EventBus.CHANNEL)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError:
                    continue
                await manager.broadcast(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Redis listener reconnecting: %s", exc)
            await asyncio.sleep(2)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(EventBus.CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass


def ensure_listener_started() -> None:
    global _listener_task
    if _listener_task is None or _listener_task.done():
        _listener_task = asyncio.create_task(_redis_listener())


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None) -> None:
    ensure_listener_started()
    # Soft auth: if token provided, validate; otherwise allow for local demo (public chat poll)
    if token:
        try:
            decode_access_token(token)
        except ValueError:
            await websocket.close(code=4401)
            return
    await manager.connect(websocket)
    try:
        while True:
            # Keepalive / ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
