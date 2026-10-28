import time
import uuid

from app.db import SessionLocal
from app.models import KnowledgeCollection, User
from app.security import hash_password


def _login(client, email="advocate@tantara.local", password="tantara-local"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_collection_pagination_ownership_membership_and_filtered_retrieval(client, monkeypatch):
    headers = _login(client)
    collections = []
    for name in ("Agreements & Contracts", "Awards & Authorities", "Pleadings & Evidence"):
        response = client.post("/api/v1/collections", headers=headers, json={"name": name})
        assert response.status_code == 201
        assert response.json()["created_at"].endswith("+00:00")
        assert response.json()["updated_at"].endswith("+00:00")
        collections.append(response.json())

    listing = client.get("/api/v1/collections?page=1&page_size=2", headers=headers)
    assert listing.status_code == 200
    assert set(listing.json()) == {"items", "total", "page", "page_size", "pages"}
    assert listing.json()["total"] == 3
    assert listing.json()["page"] == 1
    assert listing.json()["page_size"] == 2
    assert listing.json()["pages"] == 2
    assert len(listing.json()["items"]) == 2

    detail = client.get(f"/api/v1/collections/{collections[0]['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["name"] == "Agreements & Contracts"
    assert detail.json()["document_count"] == 0
    assert client.get(f"/api/v1/collections/{uuid.uuid4()}", headers=headers).status_code == 404

    researcher_id = str(uuid.uuid4())
    foreign_collection_id = str(uuid.uuid4())
    with SessionLocal() as session:
        session.add(
            User(
                id=researcher_id,
                name="Collection Researcher",
                email="collections-researcher@example.test",
                password_hash=hash_password("researcher-test-password"),
                role="researcher",
            )
        )
        session.flush()
        session.add(
            KnowledgeCollection(
                id=foreign_collection_id,
                owner_id=researcher_id,
                name="Researcher Library",
                description="Private to researcher",
            )
        )
        session.commit()
    researcher_headers = _login(client, "collections-researcher@example.test", "researcher-test-password")
    assert (
        client.get(f"/api/v1/collections/{foreign_collection_id}", headers=researcher_headers).status_code
        == 200
    )
    assert client.get(f"/api/v1/collections/{foreign_collection_id}", headers=headers).status_code == 404

    unknown = client.get(
        "/api/v1/search",
        headers=headers,
        params={"query": "Collection marker agreement", "collection_ids": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404

    document_ids = []
    for index in range(3):
        uploaded = client.post(
            "/api/v1/documents/upload",
            headers=headers,
            data={"collection_id": collections[0]["id"]},
            files={
                "file": (
                    f"collection-marker-{index}.txt",
                    f"Collection marker arbitration agreement evidence number {index}.".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 202
        document_ids.append(uploaded.json()["document_id"])
    for document_id in document_ids:
        for _ in range(100):
            job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers).json()
            if job["status"] in {"ready", "failed"}:
                break
            time.sleep(0.05)
        assert job["status"] == "ready"

    all_hits = client.get("/api/v1/search", headers=headers, params={"query": "Collection marker"}).json()
    scoped_hits = client.get(
        "/api/v1/search",
        headers=headers,
        params={"query": "Collection marker", "collection_ids": collections[0]["id"]},
    ).json()
    empty_hits = client.get(
        "/api/v1/search",
        headers=headers,
        params={"query": "Collection marker", "collection_ids": collections[1]["id"]},
    ).json()
    assert all_hits["total"] >= 1
    assert scoped_hits["total"] == 3
    assert {row["document_id"] for row in scoped_hits["items"]} == set(document_ids)
    assert empty_hits["total"] == 0
    document_alias = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "Collection marker", "collection_id": collections[0]["id"]},
    )
    assert document_alias.status_code == 200
    assert document_alias.json()["total"] == scoped_hits["total"]
    for requested, expected in ((1, 1), (2, 2)):
        limited = client.get(
            "/api/v1/search/documents",
            headers=headers,
            params={"query": "Collection marker", "collection_id": collections[0]["id"], "limit": requested},
        )
        assert limited.status_code == 200
        assert len(limited.json()["items"]) == expected
        assert limited.json()["page_size"] == requested
        assert limited.json()["total"] >= expected

    import app.main

    monkeypatch.setattr(
        app.main, "llm_answer", lambda question, hits, **kwargs: "Supported by the selected agreement."
    )
    grounded = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={
            "question": "What does the agreement say about arbitration?",
            "collection_ids": [collections[0]["id"]],
        },
    )
    assert grounded.status_code == 200
    assert grounded.json()["citations"]
    assert {citation["document_id"] for citation in grounded.json()["citations"]} <= set(document_ids)

    ask = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={
            "question": "What does the collection marker establish?",
            "collection_ids": [collections[1]["id"]],
        },
    )
    assert ask.status_code == 200
    assert ask.json()["status"] == "insufficient_evidence"
    assert ask.json()["citations"] == []
    legacy_ask = client.post(
        "/query",
        headers=headers,
        json={"question": "What does the empty collection say?", "collection_ids": [collections[1]["id"]]},
    )
    assert legacy_ask.status_code == 200
    assert legacy_ask.json()["status"] == "insufficient_evidence"
    assert legacy_ask.json()["citations"] == []

    invalid_assignment = client.patch(
        f"/api/v1/documents/{document_ids[0]}",
        headers=headers,
        json={"collection_id": str(uuid.uuid4())},
    )
    assert invalid_assignment.status_code == 404

    updated = client.patch(
        f"/api/v1/documents/{document_ids[0]}",
        headers=headers,
        json={"collection_id": collections[2]["id"]},
    )
    assert updated.status_code == 200
    assert updated.json()["collection_id"] == collections[2]["id"]

    deleted = client.delete(f"/api/v1/collections/{collections[2]['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{document_ids[0]}", headers=headers).json()["collection_id"] is None
