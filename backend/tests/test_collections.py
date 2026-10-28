import time
import uuid


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

    unknown = client.get(
        "/api/v1/search",
        headers=headers,
        params={"query": "Collection marker agreement", "collection_ids": str(uuid.uuid4())},
    )
    assert unknown.status_code == 404

    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"collection_id": collections[0]["id"]},
        files={"file": ("collection-marker.txt", b"Collection marker arbitration agreement.", "text/plain")},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["document_id"]
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
    assert scoped_hits["total"] == 1
    assert {row["document_id"] for row in scoped_hits["items"]} == {document_id}
    assert empty_hits["total"] == 0
    document_alias = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "Collection marker", "collection_id": collections[0]["id"]},
    )
    assert document_alias.status_code == 200
    assert document_alias.json()["total"] == scoped_hits["total"]

    import app.main

    monkeypatch.setattr(app.main, "llm_answer", lambda question, hits, **kwargs: "Supported by the selected agreement.")
    grounded = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "What does the agreement say about arbitration?", "collection_ids": [collections[0]["id"]]},
    )
    assert grounded.status_code == 200
    assert grounded.json()["citations"]
    assert {citation["document_id"] for citation in grounded.json()["citations"]} <= {document_id}

    ask = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "What does the collection marker establish?", "collection_ids": [collections[1]["id"]]},
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
        f"/api/v1/documents/{document_id}",
        headers=headers,
        json={"collection_id": str(uuid.uuid4())},
    )
    assert invalid_assignment.status_code == 404

    updated = client.patch(
        f"/api/v1/documents/{document_id}",
        headers=headers,
        json={"collection_id": collections[2]["id"]},
    )
    assert updated.status_code == 200
    assert updated.json()["collection_id"] == collections[2]["id"]

    deleted = client.delete(f"/api/v1/collections/{collections[2]['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers).json()["collection_id"] is None
