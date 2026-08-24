"""AI domain interfaces — Day 1 placeholders only."""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError


class AIService(ABC):
    @abstractmethod
    async def run(self, input_text: str) -> str:
        raise NotImplementedError


class AgentRuntime(ABC):
    @abstractmethod
    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
