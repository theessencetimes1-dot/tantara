import uuid

import pytest

from app.db import session_scope
from app.models import User
from app.security import create_token, hash_password


def _auth(client, email="advocate@tantara.local"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tantara-local"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _researcher_headers():
    user_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            User(
                id=user_id,
                name="Read Only",
                email=f"researcher-{user_id}@example.local",
                password_hash=hash_password("tantara-local"),
                role="researcher",
            )
        )
    return {"Authorization": f"Bearer {create_token(user_id)}"}


def _assert_list_envelope(payload):
    assert set(payload) >= {"items", "total", "page", "page_size", "pages"}
    assert isinstance(payload["items"], list)
    assert payload["total"] >= len(payload["items"])
    assert payload["page"] >= 1 and payload["page_size"] >= 1 and payload["pages"] >= 0


@pytest.mark.parametrize(
    ("path", "create", "patch"),
    [
        ("clients", {"name": "Matrix client"}, {"notes": "edited"}),
        ("cases", {"title": "Matrix case"}, {"description": "edited"}),
        ("hearings", {"title": "Matrix hearing", "at": "2030-01-01T10:00:00"}, {"notes": "edited"}),
        ("tasks", {"title": "Matrix task"}, {"notes": "edited"}),
        ("drafts", {"title": "Matrix draft", "document_type": "Pleading"}, {"content_markdown": "edited"}),
        ("bundles", {"name": "Matrix bundle"}, {"name": "Edited bundle"}),
        ("notes", {"title": "Matrix note"}, {"body": "edited"}),
        ("community/posts", {"title": "Matrix post", "body": "body"}, {"body": "edited"}),
    ],
)
def test_domain_crud_role_isolation_validation_and_pagination(client, path, create, patch):
    owner = _auth(client)
    created = client.post(f"/api/v1/{path}", headers=owner, json=create)
    assert created.status_code == (201 if path == "cases" else 200)
    record_id = created.json()["id"]
    assert client.get(f"/api/v1/{path}/{record_id}", headers=owner).status_code == 200
    assert client.patch(f"/api/v1/{path}/{record_id}", headers=owner, json=patch).status_code == 200
    listing = client.get(f"/api/v1/{path}", headers=owner).json()
    _assert_list_envelope(listing)
    out_of_range = client.get(f"/api/v1/{path}", headers=owner, params={"page": 999, "page_size": 100}).json()
    _assert_list_envelope(out_of_range)
    assert out_of_range["items"] == []

    invalid = client.post(f"/api/v1/{path}", headers=owner, json={"unexpected_field": True})
    assert invalid.status_code == 422
    assert set(invalid.json()["error"]) >= {"code", "message", "details"}

    other_owner = _researcher_headers()
    assert client.get(f"/api/v1/{path}/{record_id}", headers=other_owner).status_code == 404
    foreign_patch_status = 404 if path == "community/posts" else 403
    assert (
        client.patch(f"/api/v1/{path}/{record_id}", headers=other_owner, json=patch).status_code
        == foreign_patch_status
    )
    assert client.delete(f"/api/v1/{path}/{record_id}", headers=other_owner).status_code == 403
    foreign_create_status = 200 if path == "community/posts" else 403
    assert (
        client.post(f"/api/v1/{path}", headers=other_owner, json=create).status_code == foreign_create_status
    )

    deleted = client.delete(f"/api/v1/{path}/{record_id}", headers=owner)
    assert deleted.status_code == 200
    after_delete = client.get(f"/api/v1/{path}/{record_id}", headers=owner)
    if path == "cases":
        assert after_delete.status_code == 200 and after_delete.json()["status"] == "archived"
    else:
        assert after_delete.status_code == 404


def test_case_participant_event_strategy_and_autofill_routes(client):
    headers = _auth(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Nested case"}).json()
    cid = case["id"]
    participant = client.post(
        f"/api/v1/cases/{cid}/participants",
        headers=headers,
        json={"name": "Counsel", "party_role": "counsel"},
    )
    assert participant.status_code == 200
    pid = participant.json()["id"]
    assert (
        client.patch(
            f"/api/v1/cases/{cid}/participants/{pid}", headers=headers, json={"email": "c@example.local"}
        ).status_code
        == 200
    )
    event = client.post(
        f"/api/v1/cases/{cid}/events",
        headers=headers,
        json={"type": "notice", "occurred_at": "2026-01-02T10:00:00", "detail": "Notice sent"},
    )
    assert event.status_code == 200
    eid = event.json()["id"]
    events = client.get(f"/api/v1/cases/{cid}/events", headers=headers).json()
    _assert_list_envelope(events)
    assert events["total"] == 1
    out_of_range_events = client.get(
        f"/api/v1/cases/{cid}/events", headers=headers, params={"page": 999, "page_size": 20}
    ).json()
    _assert_list_envelope(out_of_range_events)
    assert out_of_range_events["items"] == []
    assert client.get(f"/api/v1/cases/{cid}/events/{eid}", headers=headers).status_code == 200
    assert (
        client.patch(
            f"/api/v1/cases/{cid}/events/{eid}", headers=headers, json={"detail": "Updated"}
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/cases/{cid}/events/{eid}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/cases/{cid}/participants/{pid}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/cases/{cid}/overview", headers=headers).status_code == 200
    assert client.get(f"/api/v1/cases/{cid}/autofill", headers=headers).status_code == 200
    preview = client.post(f"/api/v1/cases/{cid}/autofill/preview", headers=headers, json={"keys": ["title"]})
    assert preview.status_code == 200 and preview.json()["fields"]
    applied = client.post(
        f"/api/v1/cases/{cid}/autofill/apply",
        headers=headers,
        json={"fields": [{"key": "claimant", "value": "Claimant", "provenance": "verified"}]},
    )
    assert applied.status_code == 200 and "claimant" in applied.json()["applied"]
    assert client.get(f"/api/v1/cases/{cid}/strategy", headers=headers).status_code == 200
    updated = client.put(
        f"/api/v1/cases/{cid}/strategy",
        headers=headers,
        json={"case_theory": "Review the contract", "key_issues": ["seat"]},
    )
    assert updated.status_code == 200
    assert client.post(f"/api/v1/cases/{cid}/strategy/generate", headers=headers).status_code == 200


def test_ai_session_saved_community_and_settings_routes(client):
    headers = _auth(client)
    session = client.post("/api/v1/ai/sessions", headers=headers, json={"title": "Matrix research"})
    assert session.status_code == 200
    sid = session.json()["id"]
    sessions = client.get("/api/v1/ai/sessions", headers=headers)
    assert sessions.status_code == 200
    _assert_list_envelope(sessions.json())
    empty_sessions = client.get(
        "/api/v1/ai/sessions", headers=headers, params={"page": 999, "page_size": 20}
    ).json()
    _assert_list_envelope(empty_sessions)
    assert empty_sessions["items"] == []
    assert client.get(f"/api/v1/ai/sessions/{sid}", headers=headers).status_code == 200
    assert (
        client.patch(
            f"/api/v1/ai/sessions/{sid}", headers=headers, json={"title": "Edited research"}
        ).status_code
        == 200
    )
    message = client.post(
        f"/api/v1/ai/sessions/{sid}/messages", headers=headers, json={"question": "No evidence yet?"}
    )
    assert message.status_code == 200 and message.json()["status"] == "insufficient_evidence"
    assert (
        client.post(
            "/api/v1/ai/saved", headers=headers, json={"item_type": "research_item", "item_id": sid}
        ).status_code
        == 200
    )
    saved_response = client.get("/api/v1/ai/saved", headers=headers).json()
    _assert_list_envelope(saved_response)
    saved = saved_response["items"]
    assert saved
    empty_saved = client.get(
        "/api/v1/ai/saved", headers=headers, params={"page": 999, "page_size": 20}
    ).json()
    _assert_list_envelope(empty_saved)
    assert empty_saved["items"] == []
    assert client.delete(f"/api/v1/ai/saved/{saved[0]['id']}", headers=headers).status_code == 200
    assert client.delete(f"/api/v1/ai/sessions/{sid}", headers=headers).status_code == 200

    post = client.post(
        "/api/v1/community/posts",
        headers=headers,
        json={"title": "Matrix question", "body": "Question", "tags": ["procedure"]},
    )
    assert post.status_code == 200
    pid = post.json()["id"]
    reply = client.post(f"/api/v1/community/posts/{pid}/replies", headers=headers, json={"body": "Reply"})
    rid = reply.json()["id"]
    replies = client.get(f"/api/v1/community/posts/{pid}/replies", headers=headers).json()
    _assert_list_envelope(replies)
    assert replies["total"] == 1
    empty_replies = client.get(
        f"/api/v1/community/posts/{pid}/replies", headers=headers, params={"page": 999, "page_size": 20}
    ).json()
    _assert_list_envelope(empty_replies)
    assert empty_replies["items"] == []
    assert client.post(f"/api/v1/community/posts/{pid}/save", headers=headers).json()["saved"] is True
    assert client.delete(f"/api/v1/community/posts/{pid}/replies/{rid}", headers=headers).status_code == 200
    assert client.post(f"/api/v1/community/posts/{pid}/save", headers=headers).json()["saved"] is False

    assert client.get("/api/v1/settings/profile", headers=headers).status_code == 200
    assert (
        client.patch("/api/v1/settings/profile", headers=headers, json={"name": "Matrix User"}).status_code
        == 200
    )
    for setting in ("workspace", "appearance", "ai"):
        assert client.get(f"/api/v1/settings/{setting}", headers=headers).status_code == 200
        assert client.patch(
            f"/api/v1/settings/{setting}", headers=headers, json={"test": True}
        ).status_code in {200, 400}
    assert client.get("/api/v1/settings/database", headers=headers).status_code == 200
    assert client.get("/api/v1/settings/database/stats", headers=headers).status_code == 200
    assert client.post("/api/v1/settings/database/backup", headers=headers).status_code == 200
    security_events = client.get("/api/v1/settings/security", headers=headers)
    assert security_events.status_code == 200
    _assert_list_envelope(security_events.json())
    assert client.get("/api/v1/settings/data/import", headers=headers).json()["status"] == "not_imported"
    assert client.get("/api/v1/settings/embeddings", headers=headers).status_code == 200
    assert client.get("/api/v1/ai/status", headers=headers).status_code == 200
    assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 200
    assert client.get("/api/v1/dashboard/activity", headers=headers).status_code == 200
    assert client.get("/api/v1/dashboard/upcoming", headers=headers).status_code == 200
    assert client.get("/api/v1/calendar", headers=headers).status_code == 200
    assert client.get("/api/v1/meta/institutions", headers=headers).status_code == 200
    assert client.get("/api/v1/meta/missing", headers=headers).status_code == 404


def test_autofill_apply_parses_date_values_and_rejects_invalid_dates(client):
    headers = _auth(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Autofill date validation"})
    assert case.status_code == 201
    case_id = case.json()["id"]

    applied = client.post(
        f"/api/v1/cases/{case_id}/autofill/apply",
        headers=headers,
        json={"fields": [{"key": "notice_date", "value": "2030-01-01", "provenance": "verified"}]},
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] == ["notice_date"]
    detail = client.get(f"/api/v1/cases/{case_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["notice_date"].startswith("2030-01-01")

    invalid = client.post(
        f"/api/v1/cases/{case_id}/autofill/apply",
        headers=headers,
        json={"fields": [{"key": "limitation_date", "value": "not-a-date", "provenance": "verified"}]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["details"]["details"][0]["loc"] == ["body", "fields", "limitation_date", "value"]
