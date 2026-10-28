import json
import re
import time
import uuid
from pathlib import Path


def _auth(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _url(path):
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def _openapi():
    return json.loads((Path(__file__).resolve().parents[1] / "openapi.json").read_text())


def test_all_protected_openapi_get_operations_reject_anonymous_requests(client):
    schema = _openapi()
    protected = []
    for path, operations in schema["paths"].items():
        operation = operations.get("get")
        if operation and operation.get("security"):
            params = {}
            for param in operation.get("parameters", []):
                if param["in"] == "query" and param.get("required"):
                    kind = param.get("schema", {}).get("type")
                    params[param["name"]] = 1 if kind == "integer" else "matrix-query"
            protected.append((path, params))
    for path, params in protected:
        response = client.get(_url(path), params=params)
        assert response.status_code == 401, (path, response.status_code, response.text)


def test_all_protected_openapi_operations_reject_anonymous_requests(client):
    schema = _openapi()
    protected = []
    for path, operations in schema["paths"].items():
        for method in ("get", "post", "put", "patch", "delete"):
            operation = operations.get(method)
            if not operation or not operation.get("security"):
                continue
            params = {}
            for param in operation.get("parameters", []):
                if param["in"] == "query" and param.get("required"):
                    params[param["name"]] = "matrix-query"
            media = list(operation.get("requestBody", {}).get("content", {}))
            protected.append((method.upper(), path, params, media[0] if media else None))
    for method, path, params, media_type in protected:
        url = _url(path)
        if media_type and (
            media_type.startswith("multipart/") or media_type == "application/x-www-form-urlencoded"
        ):
            response = client.request(method, url, params=params, data={}, files={})
        elif media_type:
            response = client.request(method, url, params=params, json=12345)
        else:
            response = client.request(method, url, params=params)
        assert response.status_code == 401, (method, path, response.status_code, response.text)


def test_generated_method_inventory_covers_every_openapi_operation():
    from importlib.util import module_from_spec, spec_from_file_location

    script = Path(__file__).resolve().parents[2] / "scripts" / "write_route_inventory.py"
    spec = spec_from_file_location("route_inventory", script)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = Path(__file__).resolve().parents[2] / "docs" / "BACKEND_ROUTES.txt"
    assert inventory.read_text() == module.render_inventory()
    assert sum(1 for line in inventory.read_text().splitlines() if line and not line.startswith("#")) == 123
    matrix = Path(__file__).resolve().parents[2] / "docs" / "TEST_MATRIX.md"
    generated_section = matrix.read_text().split("## Method-level expansion\n", 1)[1]
    assert generated_section == module.render_method_matrix().split("## Method-level expansion\n", 1)[1]


def test_all_openapi_mutation_bodies_return_validation_envelope(client):
    schema = _openapi()
    owner = _auth(client)
    operations = []
    for path, methods in schema["paths"].items():
        for method in ("post", "put", "patch"):
            operation = methods.get(method)
            if operation and operation.get("requestBody"):
                content = operation["requestBody"].get("content", {})
                media_type = next(iter(content), "application/json")
                operations.append((method.upper(), path, media_type))
    for method, path, media_type in operations:
        url = _url(path)
        if media_type.startswith("multipart/") or media_type == "application/x-www-form-urlencoded":
            response = client.request(method, url, headers=owner, data={}, files={})
        else:
            response = client.request(method, url, headers=owner, json=12345)
        assert response.status_code == 422, (method, path, response.status_code, response.text)
        error = response.json().get("error", {})
        assert set(error) >= {"code", "message", "details"}, (method, path, error)


def test_all_openapi_paginated_get_routes_validate_page_bounds(client):
    schema = _openapi()
    headers = _auth(client)
    for path, operations in schema["paths"].items():
        operation = operations.get("get")
        if not operation or not any(
            param.get("name") in {"page", "page_size"} for param in operation.get("parameters", [])
        ):
            continue
        params = {"page": 0}
        for param in operation.get("parameters", []):
            if param["in"] == "query" and param.get("required"):
                params[param["name"]] = "matrix-query"
        response = client.get(_url(path), headers=headers, params=params)
        assert response.status_code == 422, (path, response.status_code, response.text)
        assert set(response.json().get("error", {})) >= {"code", "message", "details"}


def test_workspace_datetimes_accept_offsets_and_serialize_with_workspace_offset(client):
    headers = _auth(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Offset serializer case"}).json()
    created = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Offset preserving deadline", "due_at": "2026-10-27T10:00:00+05:30", "case_id": case["id"]},
    )
    assert created.status_code == 200, created.text
    assert created.json()["due_at"] == "2026-10-27T10:00:00+05:30"
    task_list = client.get("/api/v1/tasks?page_size=100", headers=headers).json()["items"]
    assert next(task for task in task_list if task["id"] == created.json()["id"])["due_at"] == "2026-10-27T10:00:00+05:30"

    hearing = client.post(
        "/api/v1/hearings",
        headers=headers,
        json={"title": "Offset preserving hearing", "at": "2026-10-27T10:00:00+05:30", "case_id": case["id"]},
    )
    assert hearing.status_code == 200, hearing.text
    assert hearing.json()["at"] == "2026-10-27T10:00:00+05:30"
    hearing_list = client.get("/api/v1/hearings?page_size=100", headers=headers).json()["items"]
    assert next(row for row in hearing_list if row["id"] == hearing.json()["id"])["at"] == "2026-10-27T10:00:00+05:30"

    utc_created = client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "UTC instant becomes workspace wall time", "due_at": "2026-10-27T04:30:00Z"},
    )
    assert utc_created.status_code == 200, utc_created.text
    assert utc_created.json()["due_at"] == "2026-10-27T10:00:00+05:30"

    calendar = client.get(
        "/api/v1/calendar",
        headers=headers,
        params={"from": "2026-10-27T00:00:00+05:30", "to": "2026-10-28T00:00:00+05:30"},
    )
    assert calendar.status_code == 200, calendar.text
    assert isinstance(calendar.json(), list)
    assert any(item["at"] == "2026-10-27T10:00:00+05:30" for item in calendar.json())
    enveloped = client.get(
        "/api/v1/calendar",
        headers=headers,
        params={"from": "2026-10-27T00:00:00+05:30", "to": "2026-10-28T00:00:00+05:30", "envelope": True},
    )
    assert enveloped.status_code == 200, enveloped.text
    assert set(enveloped.json()) == {"items", "total", "page", "page_size", "pages"}
    assert enveloped.json()["total"] == len(enveloped.json()["items"])


def test_workspace_timezone_setting_controls_datetime_offsets(monkeypatch):
    from datetime import datetime

    from app.config import get_settings
    from app.timezone import to_workspace_iso, to_workspace_naive

    get_settings.cache_clear()
    monkeypatch.setenv("TANTARA_WORKSPACE_TIME_ZONE", "America/New_York")
    try:
        instant = datetime.fromisoformat("2026-01-15T15:00:00+00:00")
        wall_time = to_workspace_naive(instant)
        assert wall_time == datetime(2026, 1, 15, 10, 0)
        assert to_workspace_iso(wall_time) == "2026-01-15T10:00:00-05:00"
    finally:
        get_settings.cache_clear()


def test_health_legacy_ingest_and_query_shapes_remain_available(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert set(health.json()) == {"status", "service", "version"}
    headers = _auth(client)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    queried = client.post("/query", headers=headers, json={"question": "What does this record establish?"})
    assert queried.status_code == 200
    assert set(queried.json()) >= {
        "status",
        "answer",
        "citations",
        "follow_ups",
        "model",
        "disclaimer",
        "research_session_id",
        "message_id",
    }
    ingested = client.post(
        "/ingest/file",
        headers=headers,
        data={"title": "Legacy upload contract", "document_type": "Other", "jurisdiction": "India"},
        files={"file": ("legacy.txt", b"Legacy ingest route contract fixture.", "text/plain")},
    )
    assert ingested.status_code == 200
    assert set(ingested.json()) >= {"document_id", "job_id", "status", "duplicate", "document"}
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{ingested.json()['document_id']}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready"


def test_draft_template_and_version_lists_have_stable_envelopes(client):
    headers = _auth(client)
    templates = client.get("/api/v1/draft-templates", headers=headers).json()
    assert set(templates) >= {"items", "total", "page", "page_size", "pages"}
    draft = client.post(
        "/api/v1/drafts", headers=headers, json={"title": "Version envelope", "document_type": "Pleading"}
    ).json()
    version = client.post(
        f"/api/v1/drafts/{draft['id']}/versions",
        headers=headers,
        json={"content_markdown": "Snapshot", "change_note": "Contract test"},
    )
    assert version.status_code == 200
    versions = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
    assert set(versions) >= {"items", "total", "page", "page_size", "pages"}


def test_case_nested_routes_never_leak_across_users(client):
    from app.db import session_scope
    from app.models import User
    from app.security import create_token, hash_password

    owner = _auth(client)
    case = client.post("/api/v1/cases", headers=owner, json={"title": "Private case routes"}).json()
    case_id = case["id"]
    participant = client.post(
        f"/api/v1/cases/{case_id}/participants",
        headers=owner,
        json={"name": "Private counsel", "party_role": "counsel"},
    ).json()
    event = client.post(
        f"/api/v1/cases/{case_id}/events",
        headers=owner,
        json={"type": "notice", "occurred_at": "2026-03-01T10:00:00", "detail": "Private event"},
    ).json()
    user_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            User(
                id=user_id,
                name="Second Advocate",
                email=f"second-{user_id}@example.local",
                password_hash=hash_password("contract-test-password"),
                role="advocate",
            )
        )
    other = {"Authorization": f"Bearer {create_token(user_id)}"}
    for method, path, body in [
        ("POST", "/api/v1/ai/ask", {"question": "What does this case say?", "case_id": case_id}),
        (
            "POST",
            "/api/v1/documents/upload",
            None,
        ),
        (
            "POST",
            "/api/v1/drafts",
            {"title": "Cross-owner draft", "document_type": "Pleading", "case_id": case_id},
        ),
        ("POST", "/api/v1/bundles", {"name": "Cross-owner bundle", "case_id": case_id}),
        (
            "POST",
            "/api/v1/hearings",
            {"title": "Cross-owner hearing", "at": "2026-03-01T10:00:00", "case_id": case_id},
        ),
        (
            "POST",
            "/api/v1/tasks",
            {"title": "Cross-owner task", "due_at": "2026-03-01T10:00:00", "case_id": case_id},
        ),
        ("POST", "/api/v1/notes", {"title": "Cross-owner note", "body": "private", "case_id": case_id}),
        (
            "POST",
            "/api/v1/community/posts",
            {"title": "Cross-owner post", "body": "private", "case_ref": case_id},
        ),
    ]:
        if path.endswith("/documents/upload"):
            response = client.post(
                path,
                headers=other,
                data={"case_id": case_id},
                files={"file": ("cross-owner.txt", b"Must not attach", "text/plain")},
            )
        else:
            response = client.request(method, path, headers=other, json=body)
        assert response.status_code == 404, (method, path, response.status_code, response.text)
    actions = [
        ("GET", f"/cases/{case_id}/overview", None),
        ("GET", f"/cases/{case_id}/events", None),
        ("GET", f"/cases/{case_id}/events/{event['id']}", None),
        ("PATCH", f"/cases/{case_id}/events/{event['id']}", {"detail": "stolen"}),
        ("DELETE", f"/cases/{case_id}/events/{event['id']}", None),
        ("POST", f"/cases/{case_id}/events", {"type": "notice", "detail": "stolen"}),
        ("POST", f"/cases/{case_id}/participants", {"name": "stolen"}),
        ("PATCH", f"/cases/{case_id}/participants/{participant['id']}", {"name": "stolen"}),
        ("DELETE", f"/cases/{case_id}/participants/{participant['id']}", None),
        ("GET", f"/cases/{case_id}/autofill", None),
        ("POST", f"/cases/{case_id}/autofill/preview", {"keys": ["title"]}),
        ("POST", f"/cases/{case_id}/autofill/apply", {"fields": []}),
        ("GET", f"/cases/{case_id}/strategy", None),
        ("PUT", f"/cases/{case_id}/strategy", {}),
        ("POST", f"/cases/{case_id}/strategy/generate", None),
    ]
    for method, path, body in actions:
        response = client.request(method, "/api/v1" + path, headers=other, json=body)
        assert response.status_code == 404, (method, path, response.status_code, response.text)


def test_document_draft_bundle_ai_and_community_subresources_are_owner_scoped(client):
    from app.db import session_scope
    from app.models import User
    from app.security import create_token, hash_password

    owner = _auth(client)
    case = client.post("/api/v1/cases", headers=owner, json={"title": "Related private case"}).json()
    client_record = client.post(
        "/api/v1/clients", headers=owner, json={"name": "Related private client"}
    ).json()
    related_case = client.post(
        "/api/v1/cases", headers=owner, json={"title": "Client relation", "client_id": client_record["id"]}
    )
    assert related_case.status_code == 200
    case_list = client.get(f"/api/v1/clients/{client_record['id']}/cases", headers=owner).json()
    assert set(case_list) >= {"items", "total", "page", "page_size", "pages"}
    assert any(item["id"] == related_case.json()["id"] for item in case_list["items"])
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=owner,
        data={"case_id": case["id"], "document_type": "Award"},
        files={"file": ("owned.txt", b"Owner only evidence for the document endpoints.", "text/plain")},
    ).json()
    did = uploaded["document_id"]
    draft = client.post(
        "/api/v1/drafts",
        headers=owner,
        json={"title": "Owner only draft", "document_type": "Pleading", "case_id": case["id"]},
    ).json()
    bundle = client.post(
        "/api/v1/bundles", headers=owner, json={"name": "Owner only bundle", "case_id": case["id"]}
    ).json()
    session = client.post("/api/v1/ai/sessions", headers=owner, json={"title": "Owner only session"}).json()
    saved = client.post(
        "/api/v1/ai/saved", headers=owner, json={"item_type": "research_item", "item_id": session["id"]}
    ).json()
    post = client.post(
        "/api/v1/community/posts", headers=owner, json={"title": "Owner only post", "body": "Private"}
    ).json()
    reply = client.post(
        f"/api/v1/community/posts/{post['id']}/replies", headers=owner, json={"body": "Private reply"}
    ).json()

    user_id = str(uuid.uuid4())
    with session_scope() as db_session:
        db_session.add(
            User(
                id=user_id,
                name="Other Advocate",
                email=f"resource-owner-{user_id}@example.local",
                password_hash=hash_password("contract-test-password"),
                role="advocate",
            )
        )
    other = {"Authorization": f"Bearer {create_token(user_id)}"}
    checks = [
        ("GET", f"/clients/{client_record['id']}/cases", None),
        ("GET", f"/documents/{did}", None),
        ("PATCH", f"/documents/{did}", {"title": "stolen"}),
        ("GET", f"/documents/{did}/job", None),
        ("GET", f"/documents/{did}/pages", None),
        ("GET", f"/documents/{did}/text", None),
        ("GET", f"/documents/{did}/file", None),
        ("GET", f"/documents/{did}/ai-read", None),
        ("POST", f"/documents/{did}/ai-read", {}),
        ("PATCH", f"/documents/{did}/extraction", {"fields": {}}),
        ("POST", f"/documents/{did}/retry", None),
        ("GET", f"/drafts/{draft['id']}/versions", None),
        ("POST", f"/drafts/{draft['id']}/versions", {"content_markdown": "stolen"}),
        ("POST", f"/drafts/{draft['id']}/regenerate-section", {"section_heading": "stolen"}),
        ("GET", f"/drafts/{draft['id']}/export", None),
        ("GET", f"/bundles/{bundle['id']}/preview", None),
        ("GET", f"/bundles/{bundle['id']}/download", None),
        ("POST", f"/bundles/{bundle['id']}/generate", None),
        ("PUT", f"/bundles/{bundle['id']}/items", {"items": []}),
        ("PUT", f"/bundles/{bundle['id']}/sections", {"sections": []}),
        ("GET", f"/ai/sessions/{session['id']}", None),
        ("PATCH", f"/ai/sessions/{session['id']}", {"title": "stolen"}),
        ("DELETE", f"/ai/sessions/{session['id']}", None),
        ("POST", f"/ai/sessions/{session['id']}/messages", {"question": "Private?"}),
        ("DELETE", f"/ai/saved/{saved['id']}", None),
        ("GET", f"/community/posts/{post['id']}", None),
        ("GET", f"/community/posts/{post['id']}/replies", None),
        ("POST", f"/community/posts/{post['id']}/replies", {"body": "stolen"}),
        ("POST", f"/community/posts/{post['id']}/save", None),
        ("DELETE", f"/community/posts/{post['id']}/replies/{reply['id']}", None),
    ]
    for method, path, body in checks:
        response = client.request(method, "/api/v1" + path, headers=other, json=body)
        assert response.status_code == 404, (method, path, response.status_code, response.text)
