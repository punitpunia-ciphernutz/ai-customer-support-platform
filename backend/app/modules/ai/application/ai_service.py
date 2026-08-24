"""Application AI service — not wired into conversations on Day 1."""

from app.modules.ai.domain.interfaces import AIService
from app.modules.ai.graphs.minimal import run_minimal_graph


class PlaceholderAIService(AIService):
    async def run(self, input_text: str) -> str:
        result = await run_minimal_graph(input_text)
        return result.get("output", "")
