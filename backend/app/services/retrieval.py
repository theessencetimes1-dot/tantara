"""Hybrid retrieval: owner-scoped lexical index plus vector search, fused by RRF.

SQLite workspaces use FTS5 + bm25 and the persistent FAISS index; PostgreSQL
workspaces use a generated tsvector column (GIN) and in-database vectors.
"""

import logging
import re

from sqlalchemy import or_, select, text

from app.db import SessionLocal
from app.embeddings import embed_query
from app.models import Document, DocumentChunk
from app.services.index_maintenance import reconcile_index
from app.services.passage_normalization import normalize_passage
from app.services.vector_store import INDEX_LOCK, store

MIN_SEMANTIC_SIMILARITY = 0.35


def _lexical_ids(session, where: str, params: dict, tokens: list[str]) -> list[str]:
    """Owner-scoped lexical candidates, ranked by the dialect's own relevance score."""
    if session.bind.dialect.name == "postgresql":
        tsquery = " OR ".join(tokens)
        if not tsquery:
            return []
        sql = (
            "SELECT c.id AS chunk_id FROM document_chunks c JOIN documents d ON d.id = c.document_id "
            f"WHERE {where} AND c.search_tsv @@ websearch_to_tsquery('simple', :query) "
            "ORDER BY ts_rank(c.search_tsv, websearch_to_tsquery('simple', :query)) DESC, c.id LIMIT 100"
        )
        return session.execute(text(sql), {**params, "query": tsquery}).scalars().all()
    fts_query = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens) or '""'
    sql = (
        "SELECT f.chunk_id FROM chunk_fts f JOIN documents d ON d.id = f.document_id "
        f"WHERE {where} AND chunk_fts MATCH :query ORDER BY bm25(chunk_fts) LIMIT 100"
    )
    return session.execute(text(sql), {**params, "query": fts_query}).scalars().all()


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
            logging.getLogger(__name__).exception("query embedding failed")
            query_vector = None
            status = "embedding_unavailable"
        clauses = [
            or_(Document.owner_id == owner_id, Document.visibility == "library"),
            Document.status == "ready",
        ]
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
                    Document.visibility,
                )
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*clauses)
            )
            rows = session.execute(stmt).all()
            allowed = {r.id: r for r in rows}
            where = "(d.owner_id=:owner OR d.visibility='library') AND d.status='ready'"
            # Hyphenated legal references are tokenized as their word parts so X-P2
            # retrieves the same evidence pool as X and does not become a dead FTS term.
            tokens = re.findall(r"[\w]{2,}", question)
            params = {"owner": owner_id}
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
                lexical = _lexical_ids(session, where, params, tokens)
            except Exception:
                lexical = []
        semantic = []
        try:
            vector_store = store()
            with INDEX_LOCK:
                with SessionLocal() as session:
                    expected_vector_ids = set(
                        session.scalars(
                            select(DocumentChunk.id)
                            .join(Document, Document.id == DocumentChunk.document_id)
                            .where(
                                Document.status == "ready",
                                DocumentChunk.embedding_blob.is_not(None),
                            )
                        ).all()
                    )
                indexed_ids = vector_store.id_set()
                if expected_vector_ids != indexed_ids:
                    logging.getLogger(__name__).warning(
                        "vector index out of sync: %s chunks in the database, %s in the %s index",
                        len(expected_vector_ids),
                        len(indexed_ids),
                        vector_store.backend,
                    )
                    try:
                        repair = reconcile_index()
                    except Exception:
                        logging.getLogger(__name__).exception("index reconciliation failed")
                        repair = {"consistent": False}
                    if not repair.get("consistent"):
                        status = "embedding_unavailable"
                if query_vector is not None:
                    semantic = vector_store.search(query_vector, vector_store.count())
        except Exception:
            # A broken vector backend must not hide searchable text from freshly
            # uploaded documents. The lexical candidates above remain usable.
            logging.getLogger(__name__).exception("semantic search unavailable; continuing with lexical results")
            semantic = []
            status = "embedding_unavailable"
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
    unique = []
    seen_passages = set()
    for score, row in fused:
        passage = normalize_passage(row.content[:900])
        if passage and passage in seen_passages:
            continue
        if passage:
            seen_passages.add(passage)
        unique.append(
            {
                "document_id": row.document_id,
                "document_title": row.title,
                "chunk_id": row.id,
                "page_number": row.page_number,
                "snippet": row.content[:900],
                "retrieval_score": score,
                "source_type": row.document_type,
                "jurisdiction": row.jurisdiction,
                "visibility": getattr(row, "visibility", "private"),
            }
        )
        if len(unique) == top_k:
            break
    return unique


retrieval_service = RetrievalService()
