"""Direct checks for the legacy RAG adapter and bearer-token security boundary."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import rag
from app.security import _b64, _key, current_user, hash_password, verify_password
from app.services.retrieval import fuse_rankings


def _row(cid, page=1):
    return SimpleNamespace(
        id=cid,
        document_id="doc-1",
        content=f"evidence {cid}",
        page_number=page,
        title="Source document",
        document_type="Agreement",
        jurisdiction="India",
    )


def test_rag_chunk_scoring_fusion_filters_semantic_padding_and_keeps_citation_contract():
    rows = {
        name: _row(name, page) for page, name in enumerate(("consensus", "fts", "semantic", "padding"), 1)
    }
    fused = fuse_rankings(
        rows,
        ["consensus", "fts"],
        ["consensus", "semantic", "padding"],
        10,
        semantic_scores={"consensus": 0.8, "semantic": 0.71, "padding": 0.04},
        min_similarity=0.3,
    )
    assert [hit["chunk_id"] for hit in fused] == ["consensus", "fts", "semantic"]
    assert fused[0]["page_number"] == 1
    assert fused[0]["score"] > fused[1]["score"] >= fused[2]["score"]
    assert fused[0]["score"] == fused[0]["retrieval_score"] == fused[0]["retreival_score"]


def test_rag_answer_citation_shape_and_empty_corpus(monkeypatch):
    monkeypatch.setattr(rag.retrieval_service, "search_with_status", lambda *_args, **_kwargs: ([], "ok"))
    empty = rag.answer("no evidence", owner_id="owner")
    assert empty["sources"] == [] and "No relevant passages" in empty["answer"]

    match = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_title": "Evidence PDF",
        "page_number": 3,
        "chunk_index": 2,
        "snippet": "The exact source passage.",
        "score": 0.83,
        "retrieval_score": 0.83,
        "retreival_score": 0.83,
        "source_type": "Agreement",
    }
    monkeypatch.setattr(
        rag.retrieval_service, "search_with_status", lambda *_args, **_kwargs: ([match], "ok")
    )
    monkeypatch.setattr("app.main.llm_answer", lambda *_args, **_kwargs: "[SOURCE chunk-1] grounded")
    result = rag.answer("question", owner_id="owner")
    assert result["sources"] == [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "title": "Evidence PDF",
            "document_type": "Agreement",
            "page_number": 3,
            "content": "The exact source passage.",
            "score": 0.83,
            "retrieval_score": 0.83,
            "retreival_score": 0.83,
        }
    ]
    monkeypatch.setattr(
        rag.retrieval_service,
        "search_with_status",
        lambda *_args, **_kwargs: ([match], "embedding_unavailable"),
    )
    degraded = rag.answer("question", owner_id="owner")
    assert degraded["status"] == "embedding_unavailable" and degraded["sources"]


def test_rag_embedding_unavailable_is_not_silently_replaced(monkeypatch):
    evidence = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "document_title": "T",
        "source_type": "Agreement",
        "page_number": 1,
        "snippet": "Source text",
        "score": 0.1,
        "retrieval_score": 0.1,
        "retreival_score": 0.1,
    }
    monkeypatch.setattr(
        rag.retrieval_service,
        "search_with_status",
        lambda *_args, **_kwargs: ([evidence], "embedding_unavailable"),
    )
    monkeypatch.setattr("app.main.llm_answer", lambda *_args, **_kwargs: "")
    result = rag.answer("question", owner_id="owner")
    assert result["status"] == "model_unavailable" and result["model"] is None
    assert result["answer"] == "" and result["sources"] == []


def test_password_hash_round_trip_and_malformed_hash():
    stored = hash_password("local test password")
    assert verify_password("local test password", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("anything", "not-a-hash")


def test_security_rejects_expired_and_tampered_tokens_without_echoing_secret(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setenv("TANTARA_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    expired = _b64(json.dumps({"sub": "unknown", "exp": int(time.time()) - 1}).encode())
    valid_window = _b64(json.dumps({"sub": "unknown", "exp": int(time.time()) + 600}).encode())
    good_expired_signature = _b64(hmac.new(_key(), f"{header}.{expired}".encode(), hashlib.sha256).digest())
    for token in (f"{header}.{expired}.{good_expired_signature}", f"{header}.{valid_window}.bad"):
        with pytest.raises(HTTPException) as exc:
            current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
        assert exc.value.status_code == 401
        assert "local test password" not in str(exc.value.detail)
        assert "secret" not in str(exc.value.detail).lower()
    config.get_settings.cache_clear()


def test_authentication_errors_never_echo_credentials(client):
    password = "never-echo-this-password"
    response = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": password}
    )
    assert response.status_code == 401
    assert password not in response.text
    bearer = "Bearer never-echo-this-token"
    protected = client.get("/api/v1/cases", headers={"Authorization": bearer})
    assert protected.status_code == 401
    assert "never-echo-this-token" not in protected.text
