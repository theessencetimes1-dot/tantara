"""Supabase Storage as a workspace object backend (production deployment).

The fake transport speaks the same shapes the live Supabase Storage API returns:
a key miss is HTTP 400 with a ``NoSuchKey`` body, uploads answer with ``Key``/
``Id``, and listing answers with base names that must be re-joined to the
requested prefix.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app import config
from app.object_store import MissingObject
from app.supabase_storage import SupabaseStore

BUCKET = "tantara-documents"


class FakeSupabase:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(f"{request.method} {path}")
        if path.startswith(f"/storage/v1/object/{BUCKET}/"):
            key = path.split(f"/storage/v1/object/{BUCKET}/", 1)[1]
            if request.method == "POST":
                self.objects[key] = request.content
                return httpx.Response(200, json={"Key": f"{BUCKET}/{key}", "Id": "id-1"})
            if request.method == "GET":
                if key not in self.objects:
                    return self.miss()
                return httpx.Response(
                    200, headers={"content-type": "application/octet-stream"}, content=self.objects[key]
                )
            if request.method == "HEAD":
                if key not in self.objects:
                    return self.miss()
                return httpx.Response(
                    200, headers={"content-length": str(len(self.objects[key]))}
                )
            if request.method == "DELETE":
                self.objects.pop(key, None)
                return httpx.Response(200, json={"message": "Successfully deleted"})
            return httpx.Response(405)
        if path.startswith(f"/storage/v1/object/info/{BUCKET}/"):
            key = path.split(f"/storage/v1/object/info/{BUCKET}/", 1)[1]
            if key not in self.objects:
                return self.miss()
            return httpx.Response(200, json={"name": key, "size": len(self.objects[key])})
        if path == f"/storage/v1/object/list/{BUCKET}":
            payload = json.loads(request.content)
            prefix = payload["prefix"]
            offset = payload.get("offset", 0)
            limit = payload.get("limit", 500)
            names = sorted(k[len(prefix) :] for k in self.objects if k.startswith(prefix))
            page = names[offset : offset + limit]
            return httpx.Response(200, json=[{"name": name, "id": name} for name in page])
        if path == "/storage/v1/bucket":
            return httpx.Response(200, json=[{"name": BUCKET, "public": False}])
        return httpx.Response(404)

    @staticmethod
    def miss() -> httpx.Response:
        return httpx.Response(
            400,
            json={"statusCode": "404", "error": "not_found", "message": "Object not found", "code": "NoSuchKey"},
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler), base_url="https://example.supabase.co")


@pytest.fixture
def store(tmp_path):
    return SupabaseStore(FakeSupabase().client(), BUCKET, tmp_path / "object-cache")


def test_roundtrip_and_cache(tmp_path):
    fake = FakeSupabase()
    store = SupabaseStore(fake.client(), BUCKET, tmp_path / "object-cache")
    key = store.put("uploads/document.bin", b"the limitation act")
    assert key == "uploads/document.bin"
    assert fake.objects == {"uploads/document.bin": b"the limitation act"}
    assert store.get(key) == b"the limitation act"
    assert store.exists(key)
    assert store.size(key) == len(b"the limitation act")
    path = store.local_path(key)
    assert path is not None and path.read_bytes() == b"the limitation act"
    store.delete(key)
    assert not store.exists(key)
    with pytest.raises(MissingObject):
        store.get(key)
    assert store.local_path(key) is None


def test_missing_object_without_cache(store):
    with pytest.raises(MissingObject):
        store.get("uploads/nope.bin")
    assert store.exists("uploads/nope.bin") is False
    assert store.size("uploads/nope.bin") is None


def test_get_falls_back_to_the_read_through_cache(store):
    """A read-through cache keeps a document open after the bucket loses it."""
    store.put("bundles/cause-list.pdf", b"pdf bytes")
    store.client = FakeSupabase().client()  # the bucket no longer holds the object
    assert store.get("bundles/cause-list.pdf") == b"pdf bytes"


def test_list_keys_rejoins_the_prefix_and_paginates(tmp_path):
    fake = FakeSupabase()
    store = SupabaseStore(fake.client(), BUCKET, tmp_path / "cache")
    # A page smaller than the page size terminates the sweep; two pages force a second call.
    for index in range(3):
        store.put(f"uploads/part-{index}.bin", b"x")
    keys = store.list_keys("uploads")
    assert keys == ["uploads/part-0.bin", "uploads/part-1.bin", "uploads/part-2.bin"]
    assert store.list_keys("bundles") == []
    assert len(store.list_keys("uploads")) == 3


def test_category_is_enforced(store):
    with pytest.raises(ValueError):
        store.list_keys("secrets")


def test_settings_accept_the_supabase_backend(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "workspace-docs")
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
        assert settings.object_storage_backend == "supabase"
        assert settings.supabase_storage_bucket == "workspace-docs"
    finally:
        config.get_settings.cache_clear()


def test_settings_reject_a_half_configured_supabase(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    config.get_settings.cache_clear()
    try:
        with pytest.raises(Exception) as caught:
            config.get_settings()
        assert "SUPABASE_URL" in str(caught.value)
    finally:
        config.get_settings.cache_clear()


def test_local_path_is_a_real_file_for_random_readers(tmp_path):
    fake = FakeSupabase()
    cache = tmp_path / "object-cache"
    store = SupabaseStore(fake.client(), BUCKET, cache)
    store.put("uploads/big.bin", b"z" * 4096)
    Path(cache, "uploads").mkdir(parents=True, exist_ok=True)
    path = store.local_path("uploads/big.bin")
    assert path is not None
    assert Path(path).stat().st_size == 4096
