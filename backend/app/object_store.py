"""Workspace object storage: local filesystem (default) or S3-compatible (MinIO).

Document uploads and generated filing bundles are addressed by a *stored key*
(``uploads/<sha256>.bin`` or ``bundles/<uuid>.pdf``). The same key is a path
below the workspace data directory on disk and an object key in the bucket, so
databases, exports and the UI keep one representation for both backends.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import threading
from pathlib import Path
from typing import Protocol

from app.config import get_settings

CATEGORIES = ("uploads", "bundles", "backups")


class MissingObject(Exception):
    """Raised when a stored key has no object behind it."""


def normalize_key(category: str, value: str | Path) -> str:
    """Validate and normalize a stored key into ``<category>/<filename>``."""
    if category not in CATEGORIES:
        raise ValueError("Unsupported storage category")
    raw = Path(str(value))
    if raw.is_absolute():
        # Compatibility for databases not yet migrated or imported from backups.
        raw = Path(category) / raw.name
    elif raw.parts and raw.parts[0] == category:
        pass
    else:
        raw = Path(category) / raw
    if len(raw.parts) != 2 or raw.parts[0] != category or not raw.parts[1]:
        raise ValueError("Unsafe stored path")
    return raw.as_posix()


class ObjectStore(Protocol):
    backend: str

    def put(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int | None: ...
    def delete(self, key: str) -> None: ...
    def local_path(self, key: str) -> Path | None: ...
    def list_keys(self, category: str) -> list[str]: ...


class FilesystemStore:
    """The original local layout: objects are files under the workspace data dir."""

    backend = "filesystem"

    def path(self, key: str) -> Path:
        normalized = normalize_key(_category(key), key)
        root = (get_settings().data_dir / _category(key)).resolve()
        resolved = (get_settings().data_dir / normalized).resolve()
        if resolved.parent != root:
            raise ValueError("Unsafe stored path")
        return resolved

    def put(self, key: str, data: bytes) -> str:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return normalize_key(_category(key), key)

    def get(self, key: str) -> bytes:
        path = self.path(key)
        if not path.is_file():
            raise MissingObject(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self.path(key).is_file()
        except ValueError:
            return False

    def size(self, key: str) -> int | None:
        try:
            path = self.path(key)
        except ValueError:
            return None
        return path.stat().st_size if path.is_file() else None

    def delete(self, key: str) -> None:
        try:
            path = self.path(key)
        except ValueError:
            return
        if path.is_file():
            path.unlink()

    def local_path(self, key: str) -> Path | None:
        try:
            path = self.path(key)
        except ValueError:
            return None
        return path if path.is_file() else None

    def list_keys(self, category: str) -> list[str]:
        if category not in CATEGORIES:
            raise ValueError("Unsupported storage category")
        root = get_settings().data_dir / category
        if not root.is_dir():
            return []
        return sorted(f"{category}/{entry.name}" for entry in root.iterdir() if entry.is_file())


class S3Store:
    """S3-compatible object storage (MinIO). A small read-through cache keeps
    random-access consumers (pypdf, FileResponse) working unchanged."""

    backend = "s3"

    def __init__(self, client, bucket: str, cache_root: Path):
        self.client = client
        self.bucket = bucket
        self.cache_root = cache_root

    # -- keys -----------------------------------------------------------------
    def _key(self, key: str) -> str:
        return normalize_key(_category(key), key)

    def _cache_path(self, key: str) -> Path:
        normalized = self._key(key)
        return self.cache_root / normalized

    # -- operations -----------------------------------------------------------
    def put(self, key: str, data: bytes) -> str:
        normalized = self._key(key)
        self.client.put_object(
            self.bucket, normalized, io.BytesIO(data), len(data), content_type="application/octet-stream"
        )
        cache = self._cache_path(normalized)
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(f".{cache.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(cache)
        return normalized

    def get(self, key: str) -> bytes:
        normalized = self._key(key)
        cache = self._cache_path(normalized)
        response = None
        try:
            response = self.client.get_object(self.bucket, normalized)
            data = response.read()
        except Exception as exc:  # noqa: BLE001 - the SDK raises many key-miss types
            if not _is_missing(exc):
                raise
            if cache.is_file():
                return cache.read_bytes()
            raise MissingObject(normalized) from exc
        finally:
            if response is not None:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                release = getattr(response, "release_conn", None)
                if callable(release):
                    release()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return data

    def exists(self, key: str) -> bool:
        try:
            normalized = self._key(key)
        except ValueError:
            return False
        try:
            self.client.stat_object(self.bucket, normalized)
            return True
        except Exception as exc:  # noqa: BLE001
            if _is_missing(exc):
                return False
            raise

    def size(self, key: str) -> int | None:
        try:
            normalized = self._key(key)
        except ValueError:
            return None
        try:
            stat = self.client.stat_object(self.bucket, normalized)
        except Exception as exc:  # noqa: BLE001
            if _is_missing(exc):
                return None
            raise
        return int(stat.size) if stat.size is not None else None

    def delete(self, key: str) -> None:
        try:
            normalized = self._key(key)
        except ValueError:
            return
        try:
            self.client.remove_object(self.bucket, normalized)
        except Exception as exc:  # noqa: BLE001
            if not _is_missing(exc):
                raise
        cache = self._cache_path(normalized)
        if cache.is_file():
            cache.unlink()

    def local_path(self, key: str) -> Path | None:
        """Materialize the object into the local read-through cache."""
        try:
            normalized = self._key(key)
        except ValueError:
            return None
        cache = self._cache_path(normalized)
        if cache.is_file():
            return cache
        try:
            self.get(normalized)
        except MissingObject:
            return None
        return cache if cache.is_file() else None

    def list_keys(self, category: str) -> list[str]:
        if category not in CATEGORIES:
            raise ValueError("Unsupported storage category")
        return [
            obj.object_name
            for obj in self.client.list_objects(self.bucket, prefix=f"{category}/", recursive=False)
            if obj.object_name
        ]


def _category(key: str) -> str:
    first = Path(str(key)).parts[0] if Path(str(key)).parts else ""
    return first if first in CATEGORIES else "uploads"


def _is_missing(exc: Exception) -> bool:
    name = type(exc).__name__
    code = str(getattr(exc, "code", "") or "")
    return name in {"NoSuchKey", "NoSuchObject", "S3Error"} and code in {
        "NoSuchKey",
        "404",
        "XMinioNoSuchKey",
        "ResourceNotFound",
    }


_client_cache: dict[tuple, object] = {}
_client_lock = threading.Lock()


def _s3_client():
    s = get_settings()
    endpoint = s.s3_endpoint.replace("https://", "").replace("http://", "").strip("/")
    key = (endpoint, s.s3_access_key, s.s3_region)
    with _client_lock:
        client = _client_cache.get(key)
        if client is None:
            from minio import Minio

            client = Minio(
                endpoint,
                access_key=s.s3_access_key,
                secret_key=s.s3_secret_key,
                region=s.s3_region or None,
                secure=bool(s.s3_secure),
            )
            _client_cache[key] = client
        return client


def ensure_bucket() -> str:
    """Create the configured bucket when it is missing (idempotent)."""
    s = get_settings()
    if s.object_storage_backend == "supabase":
        from app.supabase_storage import ensure_supabase_bucket

        return ensure_supabase_bucket()
    if s.object_storage_backend != "s3":
        return ""
    client = _s3_client()
    if not client.bucket_exists(s.s3_bucket):
        client.make_bucket(s.s3_bucket)
    return s.s3_bucket


def object_store() -> ObjectStore:
    """Return the store for the active configuration (fresh per call, cached client)."""
    s = get_settings()
    if s.object_storage_backend == "s3":
        return S3Store(_s3_client(), s.s3_bucket, s.data_dir / "object-cache")
    if s.object_storage_backend == "supabase":
        from app.supabase_storage import SupabaseStore, supabase_client

        return SupabaseStore(supabase_client(), s.supabase_storage_bucket, s.data_dir / "object-cache")
    return FilesystemStore()


def upload_key(data: bytes) -> str:
    """Content-addressed upload key, matching the historical on-disk naming."""
    return f"uploads/{hashlib.sha256(data).hexdigest()}.bin"


def reset_cache_dir() -> None:
    """Drop the read-through cache (used by tests and workspace resets)."""
    shutil.rmtree(get_settings().data_dir / "object-cache", ignore_errors=True)
