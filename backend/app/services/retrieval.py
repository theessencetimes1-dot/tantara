"""Hybrid retrieval: owner-scoped SQLite BM25 plus persistent FAISS, fused by RRF."""

import re

from sqlalchemy import select, text

from app.db import SessionLocal
from app.embeddings import embed_query
from app.models import Document, DocumentChunk
from app.services.index_maintenance import reconcile_index
from app.services.vector_store import INDEX_LOCK, store

MIN_SEMANTIC_SIMILARITY = 0.35


class RetrievalService:
    def search(
        self,
        question: str,
        owner_id: str,
        top_k: int = 5,
        case_id: str | None = None,
        jurisdiction: str | None = None,
        document_types: list[str] | None = None,
        case_ids: list[str] | None = None,
        collection_id: str | None = None,
        collection_ids: list[str] | None = None,
    ):
        results, _status = self.search_with_status(
            question,
            owner_id,
            top_k,
            case_id,
            jurisdiction,
            document_types,
            case_ids,
            collection_id,
            collection_ids,
        )
        return results

    def search_with_status(
        self,
        question: str,
        owner_id: str,
        top_k: int = 5,
        case_id: str | None = None,
        jurisdiction: str | None = None,
        document_types: list[str] | None = None,
        case_ids: list[str] | None = None,
        collection_id: str | None = None,
        collection_ids: list[str] | None = None,
    ):
        try:
            query_vector = embed_query(question)
            status = "ok"
        except Exception:
            query_vector = None
            status = "embedding_unavailable"
        clauses = [Document.owner_id == owner_id]
        if case_id:
            clauses.append(Document.case_id == case_id)
        elif case_ids:
            clauses.append(Document.case_id.in_(case_ids))
        if jurisdiction:
            clauses.append(Document.jurisdiction == jurisdiction)
        if document_types:
            clauses.append(Document.document_type.in_(document_types))
        selected_collections = list(
            dict.fromkeys(collection_ids or ([collection_id] if collection_id else []))
        )
        if selected_collections:
            clauses.append(Document.collection_id.in_(selected_collections))
        with SessionLocal() as session:
            stmt = (
                select(
                    DocumentChunk.id,
                    DocumentChunk.document_id,
                    DocumentChunk.content,
                    DocumentChunk.page_number,
                    Document.title,
                    Document.document_type,
                    Document.jurisdiction,
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*clauses)
            )
            rows = session.execute(stmt).all()
            allowed = {r.id: r for r in rows}
            where = "d.owner_id=:owner"
            # Hyphenated legal references are tokenized as their word parts so X-P2
            # retrieves the same evidence pool as X and does not become a dead FTS term.
            tokens = re.findall(r"[\w]{2,}", question)
            fts_query = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens) or '""'
            params = {"owner": owner_id, "query": fts_query}
            if case_id:
                where += " AND d.case_id=:case_id"
                params["case_id"] = case_id
            elif case_ids:
                marks = ",".join(f":case_{i}" for i in range(len(case_ids)))
                where += f" AND d.case_id IN ({marks})"
                params.update({f"case_{i}": v for i, v in enumerate(case_ids)})
            if jurisdiction:
                where += " AND d.jurisdiction=:jurisdiction"
                params["jurisdiction"] = jurisdiction
            if document_types:
                marks = ",".join(f":type_{i}" for i in range(len(document_types)))
                where += f" AND d.document_type IN ({marks})"
                params.update({f"type_{i}": v for i, v in enumerate(document_types)})
            if selected_collections:
                marks = ",".join(f":collection_{i}" for i in range(len(selected_collections)))
                where += f" AND d.collection_id IN ({marks})"
                params.update({f"collection_{i}": value for i, value in enumerate(selected_collections)})
            try:
                lexical = (
                    session.execute(
                        text(
                            f"SELECT f.chunk_id FROM chunk_fts f JOIN documents d ON d.id=f.document_id WHERE {where} AND chunk_fts MATCH :query ORDER BY bm25(chunk_fts) LIMIT 100"
                        ),
                        params,
                    )
                    .scalars()
                    .all()
                )
            except Exception:
                lexical = []
        vector_store = store()
        with INDEX_LOCK:
            with SessionLocal() as session:
                expected_vector_ids = set(
                    session.scalars(
                        select(DocumentChunk.id).join(Document, Document.id == DocumentChunk.document_id)
                    ).all()
                )
            indexed_ids = vector_store.id_set()
            if expected_vector_ids != indexed_ids:
                try:
                    repair = reconcile_index()
                except Exception:
                    repair = {"consistent": False}
                if not repair.get("consistent"):
                    status = "embedding_unavailable"
            semantic = (
                vector_store.search(query_vector, vector_store.count()) if query_vector is not None else []
            )
        semantic_scores = {cid: similarity for cid, similarity in semantic if cid in allowed}
        semantic_ids = [cid for cid in semantic_scores]
        return (
            fuse_rankings(
                allowed,
                lexical,
                semantic_ids,
                top_k,
                semantic_scores=semantic_scores,
                min_similarity=MIN_SEMANTIC_SIMILARITY,
            ),
            status,
        )


def fuse_rankings(
    rows,
    lexical_ids,
    semantic_ids,
    top_k=5,
    k=60,
    *,
    semantic_scores=None,
    min_similarity=MIN_SEMANTIC_SIMILARITY,
):
    """Fuse unique chunk candidates, keeping each source's earliest rank.

    Scoped and unscoped retrieval use this same candidate rule: duplicate IDs in
    either index pool count once at their best rank, while an ID present in both
    pools receives both reciprocal-rank contributions.
    """

    def first_ranks(candidate_ids):
        ranks = {}
        for candidate_id in candidate_ids:
            ranks.setdefault(candidate_id, len(ranks))
        return ranks

    lrank = first_ranks(lexical_ids)
    vrank = first_ranks(semantic_ids)
    ranked = []
    for cid, row in rows.items():
        score = (1 / (k + lrank[cid] + 1) if cid in lrank else 0) + (
            1 / (k + vrank[cid] + 1) if cid in vrank else 0
        )
        if score:
            ranked.append((score, row))
    ranked.sort(key=lambda x: x[0], reverse=True)
    fused = [
        (score, row)
        for score, row in ranked
        if row.id in lrank or semantic_scores is None or semantic_scores.get(row.id, 0) >= min_similarity
    ]
    return [
        {
            "document_id": r.document_id,
            "document_title": r.title,
            "chunk_id": r.id,
            "page_number": r.page_number,
            "snippet": r.content[:900],
            "retrieval_score": score,
            "source_type": r.document_type,
            "jurisdiction": r.jurisdiction,
        }
        for score, r in fused[:top_k]
    ]


retrieval_service = RetrievalService()
