"""Aggregate dependency health for /health endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

import redis.asyncio as redis
from sqlalchemy import text

from app.config import get_settings
from app.infrastructure.database.session import engine

CheckStatus = Literal["healthy", "unhealthy"]


def _ok() -> CheckStatus:
    return "healthy"


def _fail() -> CheckStatus:
    return "unhealthy"


async def _check_api() -> CheckStatus:
    # Reaching this check means the API process is serving requests.
    return _ok()


async def _check_database() -> CheckStatus:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return _ok()
    except Exception:  # noqa: BLE001 — any connectivity failure → unhealthy
        return _fail()


async def _ping_redis(url: str) -> CheckStatus:
    client: redis.Redis | None = None
    try:
        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
        await asyncio.wait_for(client.ping(), timeout=2.0)
        return _ok()
    except Exception:  # noqa: BLE001
        return _fail()
    finally:
        if client is not None:
            await client.aclose()


async def _check_redis() -> CheckStatus:
    return await _ping_redis(get_settings().redis_url)


async def _check_celery() -> CheckStatus:
    return await _ping_redis(get_settings().celery_broker_url)


def _inspect_celery_workers() -> dict[str, Any] | None:
    from app.workers.celery_app import celery_app

    inspector = celery_app.control.inspect(timeout=1.0)
    return inspector.ping()


async def _check_worker() -> CheckStatus:
    try:
        ping = await asyncio.wait_for(asyncio.to_thread(_inspect_celery_workers), timeout=3.0)
        if not ping:
            return _fail()
        return _ok()
    except Exception:  # noqa: BLE001
        return _fail()


async def _probe_gemini(api_key: str, model: str) -> None:
    from google import genai

    client = genai.Client(api_key=api_key)
    # Cheap round-trip: validates API key + model reachability without generating.
    await client.aio.models.count_tokens(model=model, contents="ping")


async def _check_llm() -> CheckStatus:
    settings = get_settings()
    if not settings.has_gemini:
        return _fail()
    try:
        await asyncio.wait_for(
            _probe_gemini(settings.gemini_api_key, settings.llm_model),
            timeout=5.0,
        )
        return _ok()
    except Exception:  # noqa: BLE001
        return _fail()


async def _check_storage() -> CheckStatus:
    settings = get_settings()
    try:
        for path_str in (settings.storage_root_dir, settings.knowledge_upload_dir):
            path = Path(path_str)
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".healthcheck"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        return _ok()
    except Exception:  # noqa: BLE001
        return _fail()


def _overall_status(*statuses: CheckStatus) -> CheckStatus:
    return "healthy" if all(s == "healthy" for s in statuses) else "unhealthy"


async def collect_health() -> dict[str, CheckStatus]:
    """Run dependency probes and return a short health payload."""
    api, db, redis_status, celery, worker, llm, storage = await asyncio.gather(
        _check_api(),
        _check_database(),
        _check_redis(),
        _check_celery(),
        _check_worker(),
        _check_llm(),
        _check_storage(),
    )
    return {
        "status": _overall_status(api, db, redis_status, celery, worker, llm, storage),
        "api": api,
        "db": db,
        "redis": redis_status,
        "celery": celery,
        "worker": worker,
        "llm": llm,
        "storage": storage,
    }
