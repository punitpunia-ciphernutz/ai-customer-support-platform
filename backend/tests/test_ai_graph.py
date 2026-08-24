import pytest

from app.modules.ai.graphs.minimal import run_minimal_graph


@pytest.mark.asyncio
async def test_minimal_graph():
    result = await run_minimal_graph("ping")
    assert "ping" in result["output"]
