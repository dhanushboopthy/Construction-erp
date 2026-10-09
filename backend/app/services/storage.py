"""Where uploaded files live. Callers use `get_storage()`; the folder on disk is today's only
adapter, and a cloud one can be added behind the same interface (Milestone 12)."""

import contextlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class LocalStorage:
    """Files in a folder. Keys are made by us (never from user input), and any key that would
    leave the folder is refused anyway."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise StorageError("The file location is not allowed")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary name and rename, so a crash never leaves half a file under the key.
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            Path(tmp).replace(path)
        except BaseException:
            with contextlib.suppress(OSError):
                Path(tmp).unlink()
            raise

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("The stored file is missing") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(Path(get_settings().storage_dir))
