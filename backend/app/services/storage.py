"""Where uploaded files live. Callers use `get_storage()`; the folder on disk is today's only
adapter, and a cloud one can be added behind the same interface (Milestone 12)."""

import contextlib
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, StorageProvider, get_settings


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


class S3Storage:
    """Files in an S3-compatible bucket. The same keys as the local folder, under an optional
    prefix. Credentials come from the environment."""

    def __init__(self, client: Any, bucket: str, prefix: str = "") -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def _key(self, key: str) -> str:
        if key.startswith("/") or ".." in key.split("/"):
            raise StorageError("The file location is not allowed")
        return f"{self._prefix}/{key}" if self._prefix else key

    def put(self, key: str, data: bytes) -> None:
        try:
            self._client.put_object(Bucket=self._bucket, Key=self._key(key), Body=data)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("The cloud storage did not accept the file") from exc

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=self._key(key))
            body: bytes = response["Body"].read()
            return body
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404"}:
                raise StorageError("The stored file is missing") from exc
            raise StorageError("The cloud storage could not be read") from exc
        except BotoCoreError as exc:
            raise StorageError("The cloud storage could not be reached") from exc

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code", "") in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StorageError("The cloud storage could not be read") from exc
        return True


def build_s3(settings: Settings) -> S3Storage:
    if not settings.s3_bucket:
        raise StorageError("S3_BUCKET is not set")
    client = boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id or None,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value() or None,
        config=BotoConfig(
            retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=20
        ),
    )
    return S3Storage(client, settings.s3_bucket, settings.s3_prefix)


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_provider is StorageProvider.S3:
        return build_s3(settings)
    return LocalStorage(Path(settings.storage_dir))
