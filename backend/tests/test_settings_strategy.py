import json
import time

from app.config import get_settings


def _auth(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_settings_preferences_password_backup_and_manifest(client, monkeypatch):
    headers = _auth(client)
    profile = client.patch("/api/v1/settings/profile", headers=headers, json={"name": "Settings tester"})
    assert profile.status_code == 200 and profile.json()["name"] == "Settings tester"
    workspace = client.patch("/api/v1/settings/workspace", headers=headers, json={"name": "Workspace A"})
    assert workspace.json()["name"] == "Workspace A"
    assert (
        client.patch("/api/v1/settings/workspace", headers=headers, json={"name": "Workspace B"}).json()[
            "name"
        ]
        == "Workspace B"
    )
    appearance = client.patch("/api/v1/settings/appearance", headers=headers, json={"theme": "dark"})
    assert appearance.json()["theme"] == "dark"
    assert (
        client.patch("/api/v1/settings/appearance", headers=headers, json={"theme": "light"}).json()["theme"]
        == "light"
    )
    ai = client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "dead-model", "top_k": 3},
    )
    assert ai.status_code == 200 and ai.json()["model"] == "dead-model"
    unsupported = client.patch("/api/v1/settings/ai", headers=headers, json={"api_key": "should-not-store"})
    assert unsupported.status_code == 400
    assert (
        client.post(
            "/api/v1/settings/password",
            headers=headers,
            json={"current_password": "incorrect", "new_password": "new-password-long"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/settings/password",
            headers=headers,
            json={"current_password": "tantara-local", "new_password": "short"},
        ).status_code
        == 400
    )
    changed = client.post(
        "/api/v1/settings/password",
        headers=headers,
        json={"current_password": "tantara-local", "new_password": "new-password-long"},
    )
    assert changed.status_code == 200 and changed.json() == {"updated": True}
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "advocate@tantara.local", "password": "new-password-long"},
        ).status_code
        == 200
    )
    stats = client.get("/api/v1/settings/database/stats", headers=headers)
    assert stats.status_code == 200 and "document_chunks" in stats.json()
    backup = client.post("/api/v1/settings/database/backup", headers=headers)
    assert backup.status_code == 200 and backup.json()["bytes"] > 0
    audit = client.get("/api/v1/settings/security", headers=headers).json()
    assert set(audit) >= {"items", "total", "page", "page_size", "pages"}
    assert audit["items"]
    assert all(item["at"].endswith("+00:00") for item in audit["items"])

    manifest = get_settings().data_dir / "corpus" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"status": "complete", "items": [{"source": "test"}]}))
    status = client.get("/api/v1/settings/data/import", headers=headers)
    assert status.json()["status"] == "complete" and status.json()["items"]
    import app.routers.settings as settings_router

    monkeypatch.setattr(
        settings_router.subprocess, "Popen", lambda *args, **kwargs: type("P", (), {"pid": 123})()
    )
    queued = client.post("/api/v1/settings/data/import", headers=headers)
    assert queued.status_code == 202 and queued.json() == {"status": "queued", "process_id": 123}


def test_strategy_evidence_autofill_skip_and_existing_preference(client):
    headers = _auth(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Evidence strategy case"}).json()
    upload = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"case_id": case["id"], "document_type": "Award", "jurisdiction": "India"},
        files={
            "file": (
                "strategy.txt",
                b"The award identifies Mumbai as the seat of arbitration for this matter.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 202
    did = upload.json()["document_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{did}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready"
    generated = client.post(f"/api/v1/cases/{case['id']}/strategy/generate", headers=headers)
    assert generated.status_code == 200
    assert generated.json()["legal_arguments"] and generated.json()["legal_arguments"][0]["support"]
    put = client.put(
        f"/api/v1/cases/{case['id']}/strategy",
        headers=headers,
        json={"case_theory": "Verified theory", "key_issues": ["seat"]},
    )
    assert put.status_code == 200 and put.json()["case_theory"] == "Verified theory"
    assert (
        client.put(
            f"/api/v1/cases/{case['id']}/strategy",
            headers=headers,
            json={"case_theory": "Updated theory", "key_issues": []},
        ).json()["case_theory"]
        == "Updated theory"
    )
    applied = client.post(
        f"/api/v1/cases/{case['id']}/autofill/apply",
        headers=headers,
        json={
            "fields": [
                {"key": "claimant", "value": "Party A", "provenance": "verified"},
                {"key": "respondent", "value": "Party B", "provenance": "ai_suggested"},
                {"key": "unsupported", "value": "ignored", "provenance": "verified"},
                {"key": "claimant", "value": "Overwrite", "provenance": "extracted_reviewed"},
            ]
        },
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] == ["claimant"]
    assert len(applied.json()["skipped"]) == 3
