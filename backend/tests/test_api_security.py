import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.models import Document, Draft, FilingBundle, User
from app.security import create_token, hash_password


def _headers(email, password):
    with TestClient(app) as c:
        login = c.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        return {"Authorization": "Bearer " + login.json()["access_token"]}


def test_cross_owner_records_are_hidden_and_researcher_is_read_only(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    ).json()
    a = {"Authorization": "Bearer " + login["access_token"]}
    case = client.post("/api/v1/cases", headers=a, json={"title": "Owned Case", "status": "active"}).json()
    from app.db import session_scope

    with session_scope() as s:
        u = User(
            id=str(uuid.uuid4()),
            name="Research User",
            email="research@example.local",
            password_hash=hash_password("password-long"),
            role="advocate",
        )
        s.add(u)
        s.flush()
        token = create_token(u.id)
        doc = Document(
            id=str(uuid.uuid4()),
            owner_id=login["user"]["id"],
            case_id=case["id"],
            title="Private PDF",
            document_type="Award",
            filename="a.pdf",
            stored_path="/tmp/a.pdf",
            content_hash=uuid.uuid4().hex,
            status="ready",
        )
        draft = Draft(
            id=str(uuid.uuid4()),
            owner_id=login["user"]["id"],
            case_id=case["id"],
            title="Private Draft",
            document_type="Pleading",
        )
        bundle = FilingBundle(
            id=str(uuid.uuid4()),
            owner_id=login["user"]["id"],
            case_id=case["id"],
            name="Private Bundle",
            settings={},
        )
        s.add_all([doc, draft, bundle])
        ids = (doc.id, draft.id, bundle.id)
        researcher = User(
            id=str(uuid.uuid4()),
            name="Read Only",
            email="read-only@example.local",
            password_hash=hash_password("password-long"),
            role="researcher",
        )
        s.add(researcher)
        s.flush()
        research_token = create_token(researcher.id)
    b = {"Authorization": "Bearer " + token}
    assert client.get(f"/api/v1/cases/{case['id']}", headers=b).status_code == 404
    assert client.patch(f"/api/v1/cases/{case['id']}", headers=b, json={"title": "steal"}).status_code == 404
    assert client.get(f"/api/v1/documents/{ids[0]}", headers=b).status_code == 404
    assert client.get(f"/api/v1/drafts/{ids[1]}", headers=b).status_code == 404
    assert client.get(f"/api/v1/bundles/{ids[2]}", headers=b).status_code == 404
    assert (
        client.post(
            "/api/v1/cases",
            headers={"Authorization": "Bearer " + research_token},
            json={"title": "Forbidden"},
        ).status_code
        == 403
    )


def test_no_evidence_is_honest_and_validation_has_error_envelope(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    ).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    response = client.post(
        "/api/v1/ai/ask", headers=headers, json={"question": "What does the evidence establish?"}
    )
    assert response.status_code == 200 and response.json()["status"] == "insufficient_evidence"
    assert response.json()["citations"] == []
    invalid = client.post("/api/v1/ai/ask", headers=headers, json={"question": "?"})
    assert invalid.status_code == 422 and "error" in invalid.json()


def test_rate_limiter_counts_in_shared_sqlite_bucket(client):
    from sqlalchemy import text

    from app.db import SessionLocal

    for _ in range(2):
        response = client.get("/api/v1/dashboard/summary")
        assert response.status_code == 401
    with SessionLocal() as session:
        count = session.scalar(
            text("SELECT SUM(count) FROM rate_buckets WHERE route_key='/api/v1/dashboard/summary'")
        )
    assert count == 2


def test_document_file_path_cannot_escape_upload_directory(client, tmp_path):
    from app.db import session_scope

    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    ).json()
    outside = tmp_path / "private.txt"
    outside.write_text("must never be served as an uploaded document")
    document_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            Document(
                id=document_id,
                owner_id=login["user"]["id"],
                title="Unsafe path fixture",
                document_type="Other",
                filename="../../private.txt",
                stored_path=str(outside),
                content_hash=uuid.uuid4().hex,
                status="ready",
            )
        )
    response = client.get(
        f"/api/v1/documents/{document_id}/file",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert response.status_code == 404
    assert b"must never be served" not in response.content
