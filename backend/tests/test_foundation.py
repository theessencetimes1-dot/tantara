import time

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.chunking import chunk_text
from app.ingestion import DocumentExtractor
from app.main import app
from app.security import hash_password, verify_password


def test_chunking_has_offsets_and_overlap():
    text = "Arbitration agreement clause. " * 80
    chunks = chunk_text(text, 300, 50)
    assert len(chunks) > 1
    assert all(text[x["start_char"] : x["end_char"]].strip() == x["content"] for x in chunks)
    assert chunks[1]["start_char"] < chunks[0]["end_char"]


def test_scrypt_password_hash():
    value = hash_password("a secure local password")
    assert verify_password("a secure local password", value)
    assert not verify_password("wrong", value)


def test_text_extractor():
    pages, warnings = DocumentExtractor().extract("sample.txt", b"arbitration text")
    assert pages[0]["text"] == "arbitration text" and not warnings
    with pytest.raises(ValueError):
        DocumentExtractor().extract("sample.exe", b"no")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    config.get_settings.cache_clear()
    db._engine = None
    with TestClient(app) as c:
        yield c
    db._engine = None
    config.get_settings.cache_clear()


def test_auth_owner_scoping_and_domain_crud(client):
    assert client.get("/api/v1/cases").status_code == 401
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    created = client.post(
        "/api/v1/cases", headers=headers, json={"title": "Example arbitration", "status": "active"}
    )
    assert created.status_code == 200
    assert client.get("/api/v1/cases?page=1&page_size=1", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/cases/not-a-record", headers=headers).status_code == 404


def test_health_and_meta(client):
    assert client.get("/health").json()["status"] == "ok"
    token = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    ).json()["access_token"]
    response = client.get("/api/v1/meta/institutions", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200 and "SIAC" in response.json()["items"]


def test_upload_job_duplicate_and_delete_consistency(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    payload = b"A sample local text document about arbitration records. " * 30
    uploaded = client.post(
        "/api/v1/documents/upload", headers=headers, files={"file": ("sample.txt", payload, "text/plain")}
    )
    assert uploaded.status_code == 202
    did = uploaded.json()["document_id"]
    from app.db import connect

    assert (
        client.post(
            "/api/v1/documents/upload",
            headers=headers,
            files={"file": ("duplicate.txt", payload, "text/plain")},
        ).status_code
        == 409
    )
    for _ in range(120):
        response = client.get(f"/api/v1/documents/{did}/job", headers=headers)
        job = response.json()
        assert response.status_code == 200, job
        assert "status" in job, job
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "ready", job
    assert client.get(f"/api/v1/documents/{did}/pages", headers=headers).json()["pages"]

    with connect() as c:
        assert (
            c.exec_driver_sql("SELECT count(*) FROM document_chunks WHERE document_id=?", (did,)).scalar() > 0
        )
    assert client.delete(f"/api/v1/documents/{did}", headers=headers).status_code == 200
    with connect() as c:
        assert (
            c.exec_driver_sql("SELECT count(*) FROM document_chunks WHERE document_id=?", (did,)).scalar()
            == 0
        )
        assert c.exec_driver_sql("SELECT count(*) FROM chunk_fts WHERE document_id=?", (did,)).scalar() == 0
