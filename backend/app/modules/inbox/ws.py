import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.infrastructure.events.bus import EventBus
from app.modules.auth.security import decode_access_token
from app.modules.widgets.visitor_token import VISITOR_TOKEN_TYPE

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._agent_connections: list[WebSocket] = []
        # Legacy unscoped public connections (internal /chat without visitor token)
        self._public_connections: list[WebSocket] = []
        # Visitor-scoped: conversation_id → sockets
        self._visitor_by_conversation: dict[str, list[WebSocket]] = {}
        self._visitor_meta: dict[WebSocket, set[str]] = {}

    async def connect_agent(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._agent_connections.append(websocket)

    async def connect_public(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._public_connections.append(websocket)

    async def connect_visitor(self, websocket: WebSocket, conversation_ids: set[str]) -> None:
        await websocket.accept()
        self._visitor_meta[websocket] = set(conversation_ids)
        for cid in conversation_ids:
            self._visitor_by_conversation.setdefault(cid, []).append(websocket)

    def subscribe_visitor(self, websocket: WebSocket, conversation_id: str) -> None:
        if websocket not in self._visitor_meta:
            self._visitor_meta[websocket] = set()
        self._visitor_meta[websocket].add(conversation_id)
        sockets = self._visitor_by_conversation.setdefault(conversation_id, [])
        if websocket not in sockets:
            sockets.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._agent_connections:
            self._agent_connections.remove(websocket)
        if websocket in self._public_connections:
            self._public_connections.remove(websocket)
        conv_ids = self._visitor_meta.pop(websocket, set())
        for cid in conv_ids:
            sockets = self._visitor_by_conversation.get(cid, [])
            if websocket in sockets:
                sockets.remove(websocket)
            if not sockets and cid in self._visitor_by_conversation:
                del self._visitor_by_conversation[cid]

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        # Agents + legacy public get all events (existing behavior)
        for ws in [*self._agent_connections, *self._public_connections]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        # Scoped visitors only get matching conversation events
        payload = message.get("payload") or {}
        conversation_id = payload.get("conversation_id")
        if conversation_id:
            for ws in list(self._visitor_by_conversation.get(conversation_id, [])):
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
async def websocket_agent(websocket: WebSocket, token: str | None = None) -> None:
    """Authenticated agent inbox socket — JWT required."""
    ensure_listener_started()
    if not token:
        await websocket.close(code=4401)
        return
    try:
        decode_access_token(token)
    except ValueError:
        await websocket.close(code=4401)
        return
    await manager.connect_agent(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/public")
async def websocket_public(websocket: WebSocket, token: str | None = None) -> None:
    """
    Public web-chat socket.

    - With visitor JWT (`typ=visitor`): conversation-scoped delivery only.
    - Without token: legacy open fan-out for internal `/chat` testing.
    """
    ensure_listener_started()
    if token:
        try:
            payload = decode_access_token(token)
        except ValueError:
            await websocket.close(code=4401)
            return
        if payload.get("typ") != VISITOR_TOKEN_TYPE:
            await websocket.close(code=4401)
            return
        conversation_ids: set[str] = set()
        if payload.get("conversation_id"):
            conversation_ids.add(str(payload["conversation_id"]))
        await manager.connect_visitor(websocket, conversation_ids)
        try:
            while True:
                raw = await websocket.receive_text()
                # Allow client to subscribe to a conversation after create
                if raw and raw != "ping":
                    try:
                        data = json.loads(raw)
                        if data.get("type") == "subscribe" and data.get("conversation_id"):
                            manager.subscribe_visitor(websocket, str(data["conversation_id"]))
                    except json.JSONDecodeError:
                        pass
        except WebSocketDisconnect:
            manager.disconnect(websocket)
        return

    # Legacy unscoped mode for /chat debugging
    await manager.connect_public(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@router.websocket("/ws/widget")
async def websocket_widget(websocket: WebSocket, token: str | None = None) -> None:
    """Visitor-token-required socket alias for embed clients."""
    if not token:
        await websocket.close(code=4401)
        return
    await websocket_public(websocket, token=token)
