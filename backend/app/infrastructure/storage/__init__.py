from functools import lru_cache

from app.config import get_settings
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    return LocalObjectStorage(settings.storage_root_dir)
