"""Day 1 placeholder interfaces — prefer concrete providers under infrastructure/."""

from abc import ABC, abstractmethod
from typing import Any


class AgentRuntime(ABC):
    @abstractmethod
    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
