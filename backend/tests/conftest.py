import pytest

from app.infrastructure.database.session import engine


@pytest.fixture(autouse=True)
async def _dispose_async_engine() -> None:
    """Avoid asyncpg 'Future attached to a different loop' across pytest-asyncio tests."""
    yield
    await engine.dispose()
