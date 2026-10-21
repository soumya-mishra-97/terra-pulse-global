"""File storage abstraction for generated report exports.

Keys are generated server-side (`reports/<report_id>.<ext>`); user input never becomes a path.
LocalFileStorage additionally resolves every key and refuses anything outside its root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

KEY_RE = re.compile(r"^[a-z]+/[a-f0-9]{32}\.(pdf|md)$")


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def _check_key(key: str) -> None:
    if not KEY_RE.match(key or ""):
        raise StorageError("invalid storage key")


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _check_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("path traversal blocked")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on POSIX

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError("file not found")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)


class S3Storage:
    """Object-storage adapter for deployment. Not exercised by the test suite (needs credentials)."""

    def __init__(self, bucket: str, prefix: str) -> None:
        import boto3  # optional dependency: pip install .[s3]

        self.bucket, self.prefix = bucket, prefix
        self.client = boto3.client("s3")

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _check_key(key)
        self.client.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data, ContentType=content_type,
                               ServerSideEncryption="AES256")

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            return self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)["Body"].read()
        except Exception as exc:
            raise StorageError("file not found") from exc

    def delete(self, key: str) -> None:
        _check_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=self.prefix + key)


def build_storage(settings) -> Storage:
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise StorageError("STORAGE_BACKEND=s3 requires S3_BUCKET")
        return S3Storage(settings.s3_bucket, settings.s3_prefix)
    return LocalFileStorage(settings.storage_dir)
