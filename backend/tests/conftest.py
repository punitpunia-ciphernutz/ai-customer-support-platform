import pytest

from app.infrastructure.database.session import engine
from app.infrastructure.events import event_bus


@pytest.fixture(autouse=True)
async def _dispose_async_engine() -> None:
    """Avoid asyncpg 'Future attached to a different loop' across pytest-asyncio tests."""
    original_publish = event_bus.publish
    await event_bus.close()
    yield
    event_bus.publish = original_publish
    from app.modules.automation.application import event_handler

    event_handler._handler_started = False
    await engine.dispose()
    await event_bus.close()
