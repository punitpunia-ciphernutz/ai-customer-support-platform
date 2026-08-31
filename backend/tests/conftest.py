import pytest

from app.infrastructure.database.session import engine
from app.infrastructure.events import event_bus


@pytest.fixture(autouse=True)
async def _dispose_async_engine() -> None:
    """Avoid asyncpg 'Future attached to a different loop' across pytest-asyncio tests."""
    await event_bus.close()
    yield
    await engine.dispose()
    await event_bus.close()
