import time


def _auth(client):
    r = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_reviewable_extraction_page_refs_range_and_hybrid_search(client):
    h = _auth(client)
    text = (
        b"Agreement clause: disputes shall be referred to arbitration. Seat of arbitration is Mumbai, India."
    )
    uploaded = client.post(
        "/api/v1/documents/upload", headers=h, files={"file": ("agreement.txt", text, "text/plain")}
    )
    assert uploaded.status_code == 202
    did = uploaded.json()["document_id"]
    for _ in range(120):
        job = client.get(f"/api/v1/documents/{did}/job", headers=h).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready" and job["pages"] == 1
    pages = client.get(f"/api/v1/documents/{did}/pages", headers=h).json()["pages"]
    assert pages[0]["page_number"] == 1
    extracted = client.get(f"/api/v1/documents/{did}/text", headers=h)
    assert extracted.status_code == 200 and "Mumbai" in extracted.json()["text"]
    preview = client.get(f"/api/v1/documents/{did}/file", headers={**h, "Range": "bytes=0-9"})
    assert preview.status_code == 206 and preview.content == text[:10]
    full_file = client.get(f"/api/v1/documents/{did}/file", headers=h)
    assert full_file.status_code == 200 and full_file.content == text
    head_file = client.head(f"/api/v1/documents/{did}/file", headers=h)
    assert head_file.status_code == 200 and int(head_file.headers["content-length"]) == len(text)
    assert head_file.content == b""
    candidate = client.post(f"/api/v1/documents/{did}/ai-read", headers=h).json()
    assert candidate["review_required"] is True
    assert candidate["fields"]["arbitration_clause"]["provenance"] == "ai_suggested"
    reviewed = client.patch(
        f"/api/v1/documents/{did}/extraction",
        headers=h,
        json={"fields": {"arbitration_clause": {"found": True, "page": 1}}},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["fields"]["arbitration_clause"]["provenance"] == "extracted_reviewed"
    results = client.get(
        "/api/v1/search/documents",
        headers=h,
        params={"query": "arbitration Mumbai", "page": 1, "page_size": 1},
    )
    assert results.status_code == 200 and results.json()["total"] >= 1
    assert set(results.json()) >= {"items", "total", "page", "page_size", "pages"}
    assert results.json()["items"][0]["document_id"] == did and results.json()["items"][0]["page_number"] == 1
    hit = results.json()["items"][0]
    assert "retreival_score" not in hit
    assert hit["retrieval_score"] > 0
    documents = client.get("/api/v1/documents", headers=h).json()
    assert set(documents) >= {"items", "total", "page", "page_size", "pages"}


def test_upload_rejections_and_duplicate_error_details(client):
    h = _auth(client)
    assert (
        client.post(
            "/api/v1/documents/upload", headers=h, files={"file": ("x.exe", b"x", "application/octet-stream")}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/documents/upload", headers=h, files={"file": ("x.pdf", b"not pdf", "application/pdf")}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/documents/upload", headers=h, files={"file": ("x.txt", b"text", "image/png")}
        ).status_code
        == 400
    )
    body = b"duplicate check is database enforced across this local workspace"
    first = client.post(
        "/api/v1/documents/upload", headers=h, files={"file": ("one.txt", body, "text/plain")}
    )
    assert first.status_code == 202
    second = client.post(
        "/api/v1/documents/upload", headers=h, files={"file": ("two.txt", body, "text/plain")}
    )
    assert second.status_code == 409
    details = second.json()["error"]["details"]["existing_document"]
    assert details["id"] == first.json()["document_id"]


def test_upload_oversize_content_is_rejected(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    h = _auth(client)
    response = client.post(
        "/api/v1/documents/upload", headers=h, files={"file": ("large.txt", b"one byte", "text/plain")}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "too_large"
