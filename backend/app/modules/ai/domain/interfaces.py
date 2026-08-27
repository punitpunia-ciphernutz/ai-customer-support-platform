"""Day 1/2 AI domain interfaces — concrete impls live under infrastructure/."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    async def structured_output(self, prompt: str, schema: type[T], **kwargs: Any) -> T:
        raise NotImplementedError

    @abstractmethod
    async def stream(self, prompt: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class Retriever(ABC):
    @abstractmethod
    async def search(self, query: str, *, organization_id: str, top_k: int | None = None) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    async def search_with_metadata(
        self, query: str, *, organization_id: str, top_k: int | None = None
    ) -> list[Any]:
        raise NotImplementedError


class AIServiceProtocol(ABC):
    @abstractmethod
    async def classify(self, message: str, **kwargs: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def summarize(self, text: str) -> str:
        raise NotImplementedError


class AgentRuntime(ABC):
    @abstractmethod
    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
