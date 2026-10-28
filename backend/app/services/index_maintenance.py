"""Rebuild and reconcile the persistent FAISS index from DB rebuild blobs."""

import numpy as np
from sqlalchemy import select

from app.db import SessionLocal
from app.models import DocumentChunk
from app.services.vector_store import store


def rebuild_index():
    with SessionLocal() as s:
        rows = s.execute(
            select(DocumentChunk.id, DocumentChunk.embedding_blob).where(
                DocumentChunk.embedding_blob.is_not(None)
            )
        ).all()
    vectors = []
    for chunk_id, blob in rows:
        vector = np.frombuffer(blob, dtype="float32")
        if vector.size:
            vectors.append((chunk_id, vector.copy()))
    store().rebuild(vectors)
    return {"chunks": len(rows), "vectors": store().count(), "consistent": len(rows) == store().count()}


def reconcile_index():
    with SessionLocal() as s:
        expected_ids = set(s.scalars(select(DocumentChunk.id)).all())
    index_ids = store().id_set()
    if index_ids != expected_ids:
        return rebuild_index()
    return {"chunks": len(expected_ids), "vectors": len(index_ids), "consistent": True}
