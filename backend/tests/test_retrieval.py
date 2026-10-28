from types import SimpleNamespace

from app.services.retrieval import fuse_rankings


def test_reciprocal_rank_fusion_prefers_consensus_and_real_rows():
    rows = {
        cid: SimpleNamespace(
            id=cid,
            document_id="doc",
            content=cid,
            page_number=i,
            title="Evidence",
            document_type="Award",
            jurisdiction="India",
        )
        for i, cid in enumerate(("both", "fts", "faiss"), 1)
    }
    hits = fuse_rankings(rows, ["both", "fts"], ["both", "faiss"], top_k=3)
    assert [x["chunk_id"] for x in hits] == ["both", "fts", "faiss"]
    assert all(x["retrieval_score"] > 0 for x in hits)
    assert hits[0]["page_number"] == 1


def test_fusion_deduplicates_each_candidate_pool_at_its_earliest_rank():
    rows = {
        cid: SimpleNamespace(
            id=cid,
            document_id="doc",
            content=cid,
            page_number=i,
            title="Evidence",
            document_type="Award",
            jurisdiction="India",
        )
        for i, cid in enumerate(("both", "fts", "faiss"), 1)
    }
    hits = fuse_rankings(rows, ["both", "both", "fts"], ["both", "faiss", "both"], top_k=3)
    assert [hit["chunk_id"] for hit in hits] == ["both", "fts", "faiss"]
    assert len({hit["chunk_id"] for hit in hits}) == len(hits)


def test_fusion_does_not_fabricate_scores_for_unretrieved_rows():
    rows = {
        "unknown": SimpleNamespace(
            id="unknown",
            document_id="doc",
            content="x",
            page_number=1,
            title="T",
            document_type="Other",
            jurisdiction="India",
        )
    }
    assert fuse_rankings(rows, [], [], 5) == []


def test_retrieval_applies_case_owner_and_metadata_filters(client):
    import time

    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    ).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    owner_id = login["user"]["id"]
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Retrieval scoped case"}).json()
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"case_id": case["id"], "document_type": "Award", "jurisdiction": "India"},
        files={
            "file": (
                "retrieval.txt",
                b"Distinct retrieval marker M4REFCODE-P2 arbitration award in India.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 202
    did = uploaded.json()["document_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{did}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready"
    plain_reference = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "M4REFCODE", "page_size": 100},
    )
    hyphenated_reference = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "M4REFCODE-P2", "page_size": 100},
    )
    assert plain_reference.status_code == hyphenated_reference.status_code == 200
    plain_pairs = {
        (item["document_id"], item["page_number"])
        for item in plain_reference.json()["items"]
        if item["document_id"] == did
    }
    hyphenated_pairs = {
        (item["document_id"], item["page_number"])
        for item in hyphenated_reference.json()["items"]
        if item["document_id"] == did
    }
    assert plain_pairs and hyphenated_pairs == plain_pairs

    from app.db import session_scope
    from app.models import User
    from app.security import create_token, hash_password
    from app.services.retrieval import retrieval_service

    single, status = retrieval_service.search_with_status(
        "Distinct retrieval marker",
        owner_id,
        case_id=case["id"],
        jurisdiction="India",
        document_types=["Award"],
    )
    assert status == "ok" and any(hit["document_id"] == did for hit in single)
    unscoped, unscoped_status = retrieval_service.search_with_status(
        "Distinct retrieval marker", owner_id, top_k=100, jurisdiction="India", document_types=["Award"]
    )
    scoped_chunk_ids = [hit["chunk_id"] for hit in single]
    unscoped_chunk_ids = [hit["chunk_id"] for hit in unscoped]
    assert unscoped_status == "ok" and any(hit["document_id"] == did for hit in unscoped)
    assert len(scoped_chunk_ids) == len(set(scoped_chunk_ids))
    assert len(unscoped_chunk_ids) == len(set(unscoped_chunk_ids))
    assert set(scoped_chunk_ids) <= set(unscoped_chunk_ids)
    page_beyond = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "Distinct retrieval marker", "page": 999},
    )
    assert page_beyond.status_code == 200
    assert page_beyond.json()["items"] == []
    assert page_beyond.json()["page"] == 999 and page_beyond.json()["total"] >= 1
    injected = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "' OR 1=1;--"},
    )
    assert injected.status_code == 200
    assert injected.json()["items"] == []
    filtered, _ = retrieval_service.search_with_status(
        "Distinct retrieval marker", owner_id, case_ids=["another-case"], jurisdiction="India"
    )
    assert filtered == []
    other_id = "retrieval-other-owner"
    with session_scope() as session:
        session.add(
            User(
                id=other_id,
                name="Other searcher",
                email="retrieval-other@example.local",
                password_hash=hash_password("retrieval-test-password"),
                role="advocate",
            )
        )
    other = {"Authorization": f"Bearer {create_token(other_id)}"}
    private_results = client.get(
        "/api/v1/search/documents", headers=other, params={"query": "Distinct retrieval marker"}
    )
    assert private_results.status_code == 200 and private_results.json()["items"] == []
