"""Supabase Storage backend for workspace objects (private bucket, REST API).

The production deployment keeps documents in Supabase Storage instead of MinIO.
Supabase's S3-compatible endpoint needs its own SigV4 access keys, which the
workspace is not issued; the project's server-side key authorises the Storage
REST API instead, so this backend speaks that API. Keys, categories, the
read-through cache and the ``MissingObject`` contract are identical to
:class:`app.object_store.S3Store`, so nothing above this module changes.
"""

from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import get_settings

PAGE_SIZE = 500
TIMEOUT_SECONDS = 30.0

_client_cache: dict[tuple, httpx.Client] = {}
_client_lock = threading.Lock()


def supabase_client() -> httpx.Client:
    """Cached HTTP client for the configured Supabase project."""
    s = get_settings()
    key = (s.supabase_url.rstrip("/"), s.supabase_service_role_key)
    with _client_lock:
        client = _client_cache.get(key)
        if client is None:
            client = httpx.Client(
                base_url=key[0],
                headers={"authorization": f"Bearer {s.supabase_service_role_key}", "apikey": key[1]},
                timeout=TIMEOUT_SECONDS,
            )
            _client_cache[key] = client
        return client


def ensure_supabase_bucket() -> str:
    """Create the workspace bucket when the project does not have it yet."""
    s = get_settings()
    client = supabase_client()
    response = client.get("/storage/v1/bucket")
    response.raise_for_status()
    for bucket in response.json():
        if bucket.get("name") == s.supabase_storage_bucket:
            return s.supabase_storage_bucket
    created = client.post(
        "/storage/v1/bucket",
        json={
            "name": s.supabase_storage_bucket,
            "public": False,
            "file_size_limit": s.max_upload_mb * 1024 * 1024,
        },
    )
    # A parallel start-up (or an operator who created the bucket first) is fine.
    if created.status_code >= 400 and "already exists" not in created.text.lower():
        created.raise_for_status()
    return s.supabase_storage_bucket


def _is_missing(response: httpx.Response) -> bool:
    """Supabase answers a key miss as 400 (sometimes 404) with a NoSuchKey body."""
    if response.status_code == 404:
        return True
    if response.status_code not in {400, 403}:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    flattened = " ".join(str(value) for value in payload.values()).lower()
    return any(marker in flattened for marker in ("not_found", "nosuchkey", "not found"))


class SupabaseStore:
    """Objects in a private Supabase Storage bucket, with a local read-through cache."""

    backend = "supabase"

    def __init__(self, client: httpx.Client, bucket: str, cache_root: Path):
        self.client = client
        self.bucket = bucket
        self.cache_root = cache_root

    # -- helpers --------------------------------------------------------------
    def _url(self, key: str) -> str:
        from app.object_store import normalize_key

        normalized = normalize_key(_category_of(key), key)
        return f"/storage/v1/object/{self.bucket}/{quote(normalized)}"

    def _cache_path(self, key: str) -> Path:
        from app.object_store import normalize_key

        return self.cache_root / normalize_key(_category_of(key), key)

    def _cache_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    # -- operations -----------------------------------------------------------
    def put(self, key: str, data: bytes) -> str:
        response = self.client.post(
            self._url(key),
            content=data,
            headers={
                "content-type": "application/octet-stream",
                "x-upsert": "true",
                "cache-control": "no-cache",
            },
        )
        response.raise_for_status()
        from app.object_store import normalize_key

        normalized = normalize_key(_category_of(key), key)
        self._cache_write(self.cache_root / normalized, data)
        return normalized

    def get(self, key: str) -> bytes:
        response = self.client.get(self._url(key))
        if response.status_code >= 400:
            if not _is_missing(response):
                response.raise_for_status()
            cache = self._cache_path(key)
            if cache.is_file():
                return cache.read_bytes()
            from app.object_store import MissingObject

            raise MissingObject(key)
        data = response.content
        self._cache_write(self._cache_path(key), data)
        return data

    def exists(self, key: str) -> bool:
        response = self.client.head(self._url(key))
        if response.status_code >= 400:
            if _is_missing(response) or response.status_code in {404, 400}:
                return False
            response.raise_for_status()
        return True

    def size(self, key: str) -> int | None:
        response = self.client.get(f"/storage/v1/object/info/{self.bucket}/{quote(_normalized(key))}")
        if response.status_code >= 400:
            if _is_missing(response):
                return None
            response.raise_for_status()
        try:
            size = response.json().get("size")
        except ValueError:
            return None
        return int(size) if size is not None else None

    def delete(self, key: str) -> None:
        response = self.client.delete(self._url(key))
        if response.status_code >= 400 and not _is_missing(response):
            response.raise_for_status()
        cache = self._cache_path(key)
        if cache.is_file():
            cache.unlink()

    def local_path(self, key: str) -> Path | None:
        """Materialize the object into the local read-through cache."""
        cache = self._cache_path(key)
        if cache.is_file():
            return cache
        from app.object_store import MissingObject

        try:
            self.get(key)
        except MissingObject:
            return None
        return cache if cache.is_file() else None

    def list_keys(self, category: str) -> list[str]:
        from app.object_store import CATEGORIES

        if category not in CATEGORIES:
            raise ValueError("Unsupported storage category")
        keys: list[str] = []
        offset = 0
        while True:
            response = self.client.post(
                f"/storage/v1/object/list/{self.bucket}",
                json={
                    "prefix": f"{category}/",
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                },
            )
            response.raise_for_status()
            rows = response.json()
            keys.extend(f"{category}/{row['name']}" for row in rows if row.get("name"))
            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return sorted(keys)


def _category_of(key: str) -> str:
    parts = Path(str(key)).parts
    return parts[0] if parts and parts[0] in ("uploads", "bundles", "backups") else "uploads"


def _normalized(key: str) -> str:
    from app.object_store import normalize_key

    return normalize_key(_category_of(key), key)
