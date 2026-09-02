from __future__ import annotations

import os
from pathlib import Path

from app.infrastructure.storage.base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    """Filesystem-backed storage for local dev and tests."""

    def __init__(self, root_dir: str) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        path = self.root / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        _ = content_type
        path = self._path(key)
        path.write_bytes(data)
        return key

    async def download(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            os.remove(path)

    async def generate_url(self, key: str, expires_seconds: int = 3600) -> str:
        _ = expires_seconds
        return f"file://{self._path(key)}"
