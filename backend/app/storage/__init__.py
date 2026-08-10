from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


@lru_cache
def get_storage() -> StorageProvider:
    return LocalStorageProvider(get_settings().storage_path)


__all__ = ["StorageProvider", "get_storage"]
