from abc import ABC, abstractmethod


class ObjectStorage(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload bytes and return storage key."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download object bytes."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete object."""

    @abstractmethod
    async def generate_url(self, key: str, expires_seconds: int = 3600) -> str:
        """Return a download URL (presigned or local path)."""
