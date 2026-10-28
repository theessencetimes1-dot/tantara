from types import SimpleNamespace

import pytest

from app.chunking import chunk_text
from app.services.retrieval import fuse_rankings


def test_page_aware_chunking_preserves_independent_page_numbers():
    pages = [(1, "A" * 2300), (2, "B" * 2300)]
    chunks = [{**chunk, "page_number": page} for page, body in pages for chunk in chunk_text(body, 500, 50)]
    assert {chunk["page_number"] for chunk in chunks} == {1, 2}
    assert all(chunk["content"].startswith("A") for chunk in chunks if chunk["page_number"] == 1)
    assert all(chunk["content"].startswith("B") for chunk in chunks if chunk["page_number"] == 2)


def test_rrf_fusion_orders_consensus_above_single_source_hits():
    rows = {
        key: SimpleNamespace(
            id=key,
            document_id="d",
            content=key,
            page_number=1,
            title="T",
            document_type="Other",
            jurisdiction="India",
        )
        for key in ("consensus", "lexical", "semantic")
    }
    hits = fuse_rankings(rows, ["consensus", "lexical"], ["consensus", "semantic"], 3)
    assert [hit["chunk_id"] for hit in hits] == ["consensus", "lexical", "semantic"]


def test_nonexistent_citation_chunk_is_rejected_by_database_foreign_key(tmp_path, monkeypatch):
    from app import config, db
    from app.db import session_scope
    from app.models import Citation

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/citation.db")
    config.get_settings.cache_clear()
    db._engine = None
    db.init_db()
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), session_scope() as session:
        session.add(
            Citation(
                id="c",
                owner_id="missing",
                message_id="missing",
                document_id="missing",
                chunk_id="missing",
                page_number=1,
                excerpt="x",
                retrieval_score=0.1,
            )
        )
    db._engine = None
    config.get_settings.cache_clear()


def test_index_rebuild_repairs_stale_ids_and_is_idempotent(client, monkeypatch):
    from app.db import session_scope
    from app.models import Document, DocumentChunk, User
    from app.services.index_maintenance import rebuild_index, reconcile_index
    from app.services.vector_store import store

    first = rebuild_index()
    assert first["consistent"]
    with session_scope() as session:
        from app.security import hash_password

        session.add(
            User(
                id="index-owner",
                name="Index owner",
                email="index-owner@example.local",
                password_hash=hash_password("index-test-password"),
                role="advocate",
            )
        )
        session.flush()
        session.add(
            Document(
                id="index-doc",
                owner_id="index-owner",
                title="Index fixture",
                document_type="Award",
                filename="fixture.txt",
                stored_path="/unused",
                content_hash="index-fixture-hash",
                status="ready",
            )
        )
        session.flush()
        import numpy as np

        session.add(
            DocumentChunk(
                id="index-chunk",
                document_id="index-doc",
                chunk_index=0,
                content="index evidence",
                page_number=1,
                start_char=0,
                end_char=14,
                embedding_blob=np.ones(384, dtype="float32").tobytes(),
            )
        )
    store().rebuild([])
    repaired = reconcile_index()
    assert repaired["consistent"] and "index-chunk" in store().id_set()
    assert rebuild_index()["consistent"]

    # Queries repair a stale FAISS map from DB vectors before degrading retrieval.
    import numpy as np

    from app.services import retrieval

    monkeypatch.setattr(retrieval, "embed_query", lambda _question: np.ones(384, dtype="float32"))
    store().rebuild([])
    hits, status = retrieval.retrieval_service.search_with_status("index evidence", "index-owner")
    assert status == "ok"
    assert [hit["chunk_id"] for hit in hits] == ["index-chunk"]
    assert store().id_set() == {"index-chunk"}


def test_security_helpers_reject_bad_credentials_and_tokens(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from app import config
    from app.security import _b64, _key, current_user, hash_password, verify_password

    monkeypatch.setenv("TANTARA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    config.get_settings.cache_clear()
    encoded = hash_password("a long secure password")
    assert verify_password("a long secure password", encoded)
    assert not verify_password("wrong password", encoded)
    assert not verify_password("x", "malformed")
    key_path = tmp_path / ".secret"
    assert len(_key()) == 48 and _key() == key_path.read_bytes()
    assert key_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(HTTPException) as missing:
        current_user(None)
    assert missing.value.status_code == 401
    with pytest.raises(HTTPException) as malformed:
        current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.token"))
    assert malformed.value.status_code == 401
    expired_body = _b64(b'{"sub":"missing-user","exp":1}')
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    token = f"{header}.{expired_body}.bad-signature"
    with pytest.raises(HTTPException) as invalid:
        current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert invalid.value.status_code == 401
    config.get_settings.cache_clear()
