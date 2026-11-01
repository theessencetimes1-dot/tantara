import logging
import time
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select


def _auth(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def _uploaded(client):
    from app.db import SessionLocal
    from app.models import Document, DocumentChunk, DocumentPage, IngestionJob, now_utc

    headers = _auth(client)
    response = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("recovery.txt", b"Agreement states disputes shall be referred to arbitration in Mumbai.", "text/plain")},
    )
    did = response.json()["document_id"]
    for _ in range(100):
        with SessionLocal() as session:
            job = session.scalar(select(IngestionJob).where(IngestionJob.document_id == did))
            if job.status in {"ready", "failed"}:
                jid = job.id
                break
        time.sleep(0.02)
    with SessionLocal() as session:
        doc = session.get(Document, did)
        page_count = len(session.scalars(select(DocumentPage).where(DocumentPage.document_id == did)).all())
        chunk_count = len(session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == did)).all())
        job = session.get(IngestionJob, jid)
        return headers, did, jid, doc.owner_id, page_count, chunk_count, now_utc


def test_recovery_sweep_reprocesses_stale_job_idempotently(client):
    from app.db import SessionLocal
    from app.models import Document, DocumentChunk, DocumentPage, IngestionJob
    from app.routers.documents import sweep_ingestion_jobs

    _, did, jid, _, before_pages, before_chunks, now_utc = _uploaded(client)
    with SessionLocal() as session:
        doc, job = session.get(Document, did), session.get(IngestionJob, jid)
        doc.status = "extracting"
        job.status = "extracting"
        job.updated_at = now_utc() - timedelta(seconds=601)
        session.commit()
    sweep_ingestion_jobs()
    sweep_ingestion_jobs()
    with SessionLocal() as session:
        assert session.get(Document, did).status == "ready"
        assert session.get(IngestionJob, jid).status == "ready"
        assert len(session.scalars(select(DocumentPage).where(DocumentPage.document_id == did)).all()) == before_pages
        assert len(session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == did)).all()) == before_chunks


def test_recovery_skips_fresh_claim(client):
    from app.db import SessionLocal
    from app.models import Document, IngestionJob, now_utc
    from app.routers.documents import _claim_job, sweep_ingestion_jobs

    _, did, jid, _, *_ = _uploaded(client)
    with SessionLocal() as session:
        session.get(Document, did).status = "extracting"
        job = session.get(IngestionJob, jid)
        job.status = "extracting"
        job.updated_at = now_utc()
        session.commit()
    assert _claim_job(jid) is False
    sweep_ingestion_jobs()
    with SessionLocal() as session:
        assert session.get(Document, did).status == "extracting"
        assert session.get(IngestionJob, jid).status == "extracting"


def test_ai_read_uses_model_and_accepts_fenced_json(client, monkeypatch):
    from app import main

    headers, did, *_ = _uploaded(client)
    monkeypatch.setattr(
        main,
        "llm_answer",
        lambda *args, **kwargs: '```json\n{"parties":[{"name":"A Ltd","role":"seller"}],"key_dates":[{"date":"2025-01-02","description":"Signed"}]}\n```',
    )
    result = client.post(f"/api/v1/documents/{did}/ai-read", headers=headers).json()
    assert result["status"] == "model_generated"
    assert result["fields"]["parties"]["value"] == [{"name": "A Ltd", "role": "seller"}]
    assert result["fields"]["arbitration_clause"]["value"]["quote"]
    assert all(value["review_required"] for value in result["fields"].values())


def test_ai_read_falls_back_to_regex_on_model_failure(client, monkeypatch):
    from app import main

    headers, did, *_ = _uploaded(client)
    monkeypatch.setattr(main, "llm_answer", lambda *args, **kwargs: None)
    result = client.post(f"/api/v1/documents/{did}/ai-read", headers=headers).json()
    assert result["status"] == "local_extraction"
    assert result["fields"]["arbitration_clause"]["value"]["found"] is True


def test_llm_failure_logs_provider_without_raising(monkeypatch, caplog):
    from app import main

    settings = SimpleNamespace(
        ai_provider="local", local_llm_model="test-model", local_llm_base_url="http://unused", local_llm_timeout=1
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    logger = logging.getLogger("app.main")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "propagate", True)
    previous_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    monkeypatch.setattr(logging.root.manager, "disable", previous_disable)
    monkeypatch.setattr(main.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    with caplog.at_level(logging.WARNING, logger="app.main"):
        assert main.llm_answer("question", []) is None
    assert "provider=local" in caplog.text and "RuntimeError" in caplog.text


def test_rate_limit_keys_authenticated_users_separately_and_anonymous_by_ip(client):
    from sqlalchemy import text

    from app.db import SessionLocal

    first = _auth(client)
    from app.db import session_scope
    from app.models import User
    from app.security import hash_password

    with session_scope() as session:
        if not session.scalar(select(User).where(User.email == "rate-researcher@example.test")):
            session.add(User(
                id="rate-limit-test-researcher", name="Rate Researcher", email="rate-researcher@example.test",
                password_hash=hash_password("tantara-local"), role="researcher",
            ))
    second_login = client.post(
        "/api/v1/auth/login", json={"email": "rate-researcher@example.test", "password": "tantara-local"}
    )
    assert second_login.status_code == 200
    second = {"Authorization": "Bearer " + second_login.json()["access_token"]}
    for headers in (first, second):
        assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 200
    with SessionLocal() as session:
        users = session.execute(
            text("SELECT DISTINCT client_key FROM rate_buckets WHERE route_key='/api/v1/dashboard/summary'")
        ).scalars().all()
    assert len(users) == 2 and all(key.startswith("u:") for key in users)

    client.get("/api/v1/auth/login", headers={"X-Forwarded-For": "198.51.100.10, 10.0.0.1"})
    with SessionLocal() as session:
        anonymous = session.execute(
            text("SELECT DISTINCT client_key FROM rate_buckets WHERE route_key='/api/v1/auth/login'")
        ).scalars().all()
    assert "ip:198.51.100.10" in anonymous


def test_rate_limit_ignores_preflight_and_upload_returns_retry_after(client, monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy import text

    from app import main
    from app.db import SessionLocal

    headers = _auth(client)
    settings = SimpleNamespace(
        rate_limit_authenticated_per_minute=1200,
        rate_limit_upload_per_minute=1,
        rate_limit_anonymous_auth_per_minute=20,
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    with SessionLocal() as session:
        before = session.scalar(
            text("SELECT COALESCE(SUM(count), 0) FROM rate_buckets WHERE route_key='/api/v1/documents/upload'")
        )
    preflight = client.options("/api/v1/documents/upload")
    assert preflight.status_code != 429
    with SessionLocal() as session:
        after = session.scalar(
            text("SELECT COALESCE(SUM(count), 0) FROM rate_buckets WHERE route_key='/api/v1/documents/upload'")
        )
    assert after == before
    file = {"file": ("limit.txt", b"rate limit upload", "text/plain")}
    assert client.post("/api/v1/documents/upload", headers=headers, files=file).status_code == 202
    response = client.post(
        "/api/v1/documents/upload", headers=headers,
        files={"file": ("limit2.txt", b"rate limit upload two", "text/plain")},
    )
    assert response.status_code == 429
    assert response.headers["Retry-After"].isdigit()
    assert response.json() == {
        "error": {"code": "rate_limited", "message": "Request rate limit exceeded"}
    }


def test_draft_unavailable_is_explicit_and_generated_draft_has_confirmations(client, monkeypatch):
    from app import main

    headers = _auth(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Draft generation test"}).json()
    _, did, *_ = _uploaded(client)
    from app.db import SessionLocal
    from app.models import Document

    with SessionLocal() as session:
        document = session.get(Document, did)
        document.case_id = case["id"]
        session.commit()
    payload = {
        "case_id": case["id"], "document_type": "Statement of Claim",
        "source_document_ids": [did], "instructions": "The invoice date and number are missing.",
    }
    monkeypatch.setattr(main, "llm_answer", lambda *args, **kwargs: None)
    unavailable = client.post("/api/v1/drafts/generate", headers=headers, json=payload).json()
    assert unavailable["status"] == "model_unavailable"
    assert unavailable["message"] and unavailable["content_markdown"] == ""
    assert unavailable["citations"]

    monkeypatch.setattr(
        main, "llm_answer",
        lambda prompt, hits, **kwargs: "## Demand\n[TO BE CONFIRMED] Invoice date and number.\n## Response deadline\nPlease respond by [TO BE CONFIRMED].\n## Arbitration\n[TO BE CONFIRMED].\nSource [" + hits[0]["chunk_id"] + "]",
    )
    available = client.post("/api/v1/drafts/generate", headers=headers, json=payload).json()
    assert available["status"] == "ok"
    assert available["content_markdown"].count("[TO BE CONFIRMED]") >= 3
    assert available["citations"]


def test_ai_status_reports_provider_and_cached_probe(client, monkeypatch):
    from app import main

    headers = _auth(client)
    calls = []
    monkeypatch.setattr(main, "llm_answer", lambda *args, **kwargs: calls.append(1) or "OK")
    main._ai_probe_cache.clear()
    first = client.get("/api/v1/ai/status", headers=headers).json()["llm"]
    second = client.get("/api/v1/ai/status", headers=headers).json()["llm"]
    assert first["provider"] == "local" and first["reachable"] is True
    assert "enable_cloud_providers" in first and first["model"]
    assert len(calls) == 1 and second["reachable"] is True
