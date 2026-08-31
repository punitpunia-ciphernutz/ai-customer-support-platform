"""Celery asyncio.run + shared async engine must not leak across event loops."""

from sqlalchemy import text

from app.workers.tasks import run_async


def test_run_async_survives_multiple_event_loops() -> None:
    """Regression: Celery calls asyncio.run per task; pooled asyncpg connections
    from the previous loop must not crash the next task.
    """

    async def ping() -> str:
        from app.infrastructure.database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            return str(result.scalar_one())

    assert run_async(ping) == "1"
    assert run_async(ping) == "1"
