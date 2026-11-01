"""Page-aware upload, async ingestion, file access, and AI Read routes."""

import asyncio
import hashlib
import logging
import mimetypes
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update

from app.chunking import chunk_text
from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.embeddings import embed_documents
from app.ingestion import DocumentExtractor, DocumentStorage
from app.models import (
    AppPreference,
    Case,
    Document,
    DocumentChunk,
    DocumentPage,
    ExtractionField,
    IngestionJob,
)
from app.object_store import MissingObject, object_store
from app.repositories.domain import get_owned, serialize
from app.repositories.domain import update as repo_update
from app.routers.domain import owned, readable_document
from app.security import current_user, require_roles
from app.services.audit import record
from app.services.vector_store import INDEX_LOCK, store

router = APIRouter(prefix="/api/v1", tags=["documents"])

ADMIN_KNOWLEDGE_FOLDERS = {
    "01_INDIAN_PRIMARY_ACTS": "Indian primary acts",
    "02_AMENDMENTS_AND_NOTIFICATIONS": "Amendments and notifications",
    "03_ARBITRATION_RULES_AND_REFERENCE": "Arbitration rules and reference",
}


class NoExtractableTextError(ValueError):
    """An uploaded file has no text that can be added to search."""


class DocumentReadError(ValueError):
    """An uploaded file could not be parsed as a supported document."""


class EmbeddingCreationError(ValueError):
    """Readable document text could not be converted into search embeddings."""


class SearchIndexWriteError(ValueError):
    """Precomputed embeddings could not be committed to the search index."""


def indexing_confidence(pages):
    """Estimate extraction coverage per page; this is a content-quality heuristic, not legal certainty."""
    scored_pages = []
    for page in pages:
        text = page.get("text") or ""
        word_count = len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE))
        score = min(100.0, word_count * 0.5)
        ocr_confidence = page.get("ocr_confidence")
        if ocr_confidence is not None:
            ocr_score = max(0.0, min(100.0, float(ocr_confidence) * 100))
            score = score * 0.75 + ocr_score * 0.25
        warnings = page.get("warnings") or []
        if isinstance(warnings, str):
            warnings = [warnings]
        score = max(0.0, score - min(20.0, len(warnings) * 10.0))
        scored_pages.append(
            {
                "page_number": page.get("page_number"),
                "word_count": word_count,
                "score": round(score),
                "ocr_confidence": ocr_confidence,
                "warning_count": len(warnings),
            }
        )
    return {
        "score": round(sum(page["score"] for page in scored_pages) / len(scored_pages)) if scored_pages else None,
        "page_count": len(scored_pages),
        "pages": scored_pages,
    }


class Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tantara-ingest")
EMBEDDING_LOCK = threading.Lock()


def _job_update(job_id, **values):
    with session_scope() as s:
        job = s.get(IngestionJob, job_id)
        if job:
            for k, v in values.items():
                setattr(job, k, v)


def _claim_job(job_id):
    from datetime import timedelta

    from app.models import now_utc

    cutoff = now_utc() - timedelta(seconds=get_settings().ingestion_claim_timeout_seconds)
    with session_scope() as s:
        claimed = s.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == job_id,
                or_(
                    IngestionJob.status == "queued",
                    IngestionJob.status.in_(["extracting", "indexing", "running"])
                    & (IngestionJob.updated_at < cutoff),
                ),
            )
            .values(status="running", updated_at=now_utc())
        ).rowcount
        return bool(claimed)


def prepare_document(filename, data):
    """Extract readable text and create every embedding before storage accepts an upload."""
    try:
        pages, warnings = DocumentExtractor().extract(filename, data)
    except Exception as exc:
        raise DocumentReadError(
            "This file could not be read as a document. It was not stored."
        ) from exc
    all_text = "\n".join(page["text"] for page in pages)
    if not all_text.strip():
        error = NoExtractableTextError(
            "No readable text was found. The document was not stored. "
            "Upload a text-readable file or run OCR, then try again."
        )
        error.pages, error.warnings = pages, warnings
        raise error

    chunks = []
    offset = 0
    for page in pages:
        for chunk in chunk_text(
            page["text"], get_settings().chunk_size_chars, get_settings().chunk_overlap_chars
        ):
            chunks.append(
                {
                    **chunk,
                    "page_number": page["page_number"],
                    "start_char": chunk["start_char"] + offset,
                    "end_char": chunk["end_char"] + offset,
                }
            )
        offset += len(page["text"]) + 1
    if not chunks:
        raise NoExtractableTextError("No searchable text was found. The document was not stored.")

    try:
        with EMBEDDING_LOCK:
            vectors = embed_documents([chunk["content"] for chunk in chunks])
        if len(vectors) != len(chunks) or any(
            len(vector) != get_settings().embedding_dimensions for vector in vectors
        ):
            raise ValueError("embedding provider returned incomplete or incompatible vectors")
    except Exception as exc:
        raise EmbeddingCreationError(
            "Readable text was found, but search embeddings could not be created. "
            "The document was not stored. Check the embedding service and try again."
        ) from exc

    return pages, warnings, all_text, chunks, vectors


def process_job(doc_id, job_id, owner_id=None, data=None, filename=None, prepared=None):
    if not _claim_job(job_id):
        return
    with SessionLocal() as s:
        doc_info = s.get(Document, doc_id)
        if doc_info is None:
            return
        owner_id = owner_id or doc_info.owner_id
        filename = filename or doc_info.filename
        stored_path = doc_info.stored_path
    pages = []
    warnings = []
    try:
        if isinstance(
            prepared,
            (DocumentReadError, NoExtractableTextError, EmbeddingCreationError),
        ):
            pages = getattr(prepared, "pages", [])
            warnings = getattr(prepared, "warnings", [])
            raise prepared
        if data is None:
            data = object_store().get(stored_path)
        if prepared is None:
            _job_update(
                job_id,
                status="extracting",
                progress=10,
                steps=[{"key": "extract", "label": "Checking readable text", "state": "active"}],
            )
            heartbeat_stop = threading.Event()

            def heartbeat():
                from app.models import now_utc

                while not heartbeat_stop.wait(15):
                    _job_update(job_id, progress=10, updated_at=now_utc())

            heartbeat_thread = threading.Thread(target=heartbeat, name="tantara-ingest-heartbeat", daemon=True)
            heartbeat_thread.start()
            try:
                prepared = prepare_document(filename, data)
            finally:
                heartbeat_stop.set()
                heartbeat_thread.join(timeout=1)
        pages, warnings, all_text, chunks, vectors = prepared
        confidence = indexing_confidence(pages)
        _job_update(
            job_id,
            status="indexing",
            progress=75,
            steps=[
                {"key": "extract", "label": "Readable text confirmed", "state": "complete"},
                {"key": "embed", "label": "Creating embeddings", "state": "complete"},
                {"key": "index", "label": "Writing search index", "state": "active"},
            ],
        )
        indexed = []
        with INDEX_LOCK:
            with SessionLocal() as s:
                old_ids = s.scalars(
                    select(DocumentChunk.id).where(DocumentChunk.document_id == doc_id)
                ).all()
            if old_ids:
                try:
                    store().remove(old_ids)
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Could not remove stale semantic vectors for document %s (%s)",
                        doc_id,
                        type(exc).__name__,
                    )
            with session_scope() as s:
                s.query(DocumentPage).filter(DocumentPage.document_id == doc_id).delete()
                s.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
                doc = s.get(Document, doc_id)
                doc.text_content = all_text
                doc.page_count = len(pages)
                doc.warnings = warnings
                doc.status = "processing"
                doc.citation_metadata = {
                    **(doc.citation_metadata or {}),
                    "indexing_confidence": confidence,
                }
                for p in pages:
                    s.add(
                        DocumentPage(
                            id=str(uuid.uuid4()),
                            owner_id=owner_id,
                            document_id=doc_id,
                            page_number=p["page_number"],
                            text=p["text"],
                            ocr_confidence=p.get("ocr_confidence"),
                            warnings=p.get("warnings", []),
                            is_demo=doc.is_demo,
                        )
                    )
                for ix, (ch, vec) in enumerate(zip(chunks, vectors, strict=True)):
                    row = DocumentChunk(
                        id=str(uuid.uuid4()),
                        document_id=doc_id,
                        chunk_index=ix,
                        content=ch["content"],
                        page_number=ch["page_number"],
                        start_char=ch["start_char"],
                        end_char=ch["end_char"],
                        embedding_blob=__import__("numpy").asarray(vec, dtype="float32").tobytes(),
                        is_demo=doc.is_demo,
                    )
                    s.add(row)
                    indexed.append((row.id, vec))
            if indexed:
                try:
                    store().add(indexed)
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Could not add semantic vectors for document %s (%s)",
                        doc_id,
                        type(exc).__name__,
                    )
                    raise SearchIndexWriteError(
                        "Embeddings were created, but the search index could not be written. Retry indexing."
                    ) from exc
            with session_scope() as s:
                doc = s.get(Document, doc_id)
                if doc:
                    doc.status = "ready"
        _job_update(
            job_id,
            status="ready",
            progress=100,
            steps=[
                {"key": "extract", "label": "Extracting pages", "state": "complete"},
                {"key": "embed", "label": "Creating local embeddings", "state": "complete"},
                {"key": "index", "label": "Writing search index", "state": "complete"},
            ],
            warnings=warnings,
            pages=len(pages),
            chars=len(all_text),
            error=None,
        )
    except Exception as exc:
        cause = exc.__cause__ if isinstance(exc, DocumentReadError) else None
        logging.warning(
            "Document processing failed (%s)", type(cause or exc).__name__
        )
        with session_scope() as s:
            doc = s.get(Document, doc_id)
            if doc:
                doc.status = "failed"
                doc.warnings = warnings
                s.query(DocumentPage).filter(DocumentPage.document_id == doc_id).delete()
                for page in pages:
                    if page.get("warnings") or not page.get("text", "").strip():
                        s.add(
                            DocumentPage(
                                id=str(uuid.uuid4()),
                                owner_id=owner_id,
                                document_id=doc_id,
                                page_number=page["page_number"],
                                text=page.get("text", ""),
                                ocr_confidence=page.get("ocr_confidence"),
                                warnings=page.get("warnings", []),
                            )
                        )
        error_message = (
            str(exc)
            if isinstance(
                exc,
                (DocumentReadError, NoExtractableTextError, EmbeddingCreationError, SearchIndexWriteError),
            )
            else f"{type(exc).__name__}: processing failed"
        )
        _job_update(
            job_id,
            status="failed",
            progress=0,
            error=error_message,
            warnings=warnings,
        )


def sweep_ingestion_jobs():
    """Requeue all recoverable jobs from durable object storage."""
    try:
        with SessionLocal() as s:
            jobs = s.execute(
                select(IngestionJob.id, IngestionJob.document_id)
                .join(Document, Document.id == IngestionJob.document_id)
                .where(
                    IngestionJob.status.in_(["queued", "extracting", "indexing", "running"]),
                    Document.status.notin_(["ready", "failed"]),
                )
            ).all()
        for job_id, doc_id in jobs:
            try:
                process_job(doc_id, job_id)
            except Exception:
                logging.getLogger(__name__).exception("Ingestion recovery attempt failed for job %s", job_id)
    except Exception:
        logging.getLogger(__name__).exception("Ingestion recovery sweep failed")


async def ingestion_recovery_loop():
    """Run a startup recovery and periodic sweeps without blocking the event loop."""
    while True:
        await asyncio.to_thread(sweep_ingestion_jobs)
        await asyncio.sleep(45)


@router.post("/documents/upload", status_code=202)
async def upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    document_type: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    case_id: str | None = Form(None),
    collection_id: str | None = Form(None),
    user=Depends(current_user),
):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    filename = Path(file.filename or "upload").name
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".docx", ".txt", ".md"}:
        raise HTTPException(400, "Unsupported document type")
    accepted_types = {
        ".pdf": {"application/pdf", "application/octet-stream"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
        },
        ".txt": {"text/plain", "application/octet-stream"},
        ".md": {"text/markdown", "text/plain", "application/octet-stream"},
    }
    content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if content_type not in accepted_types[ext]:
        raise HTTPException(400, "Unsupported content type for document extension")
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")
    if not data:
        raise HTTPException(400, "Uploaded file is empty")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(400, "File content does not match its extension")
    if ext == ".docx":
        try:
            import io
            import zipfile

            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "[Content_Types].xml" not in z.namelist() or "word/document.xml" not in z.namelist():
                    raise ValueError()
        except Exception:
            raise HTTPException(400, "File content does not match its extension")
    if ext in {".txt", ".md"}:
        try:
            if b"\x00" in data:
                raise UnicodeDecodeError("utf8", data, 0, 1, "NUL")
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "Text document must be valid UTF-8")
    filename = "".join(ch for ch in filename if ch.isprintable())[:200] or "upload"
    if case_id:
        with SessionLocal() as s:
            owned(s, Case, case_id, user)
    if collection_id:
        from app.models import KnowledgeCollection

        with SessionLocal() as s:
            owned(s, KnowledgeCollection, collection_id, user)
    digest = hashlib.sha256(data).hexdigest()
    with SessionLocal() as s:
        old = s.scalar(
            select(Document)
            .where(
                Document.content_hash == digest,
                or_(Document.owner_id == user["id"], Document.visibility == "library"),
            )
            .order_by(Document.visibility.desc())
        )
    if old:
        is_library = old.visibility == "library"
        raise HTTPException(
            409,
            {
                "message": "Already in the law library" if is_library else "Duplicate document",
                "existing_document": {"id": old.id, "title": old.title},
            },
        )
    try:
        prepared = await asyncio.to_thread(prepare_document, filename, data)
    except NoExtractableTextError as exc:
        prepared = exc
    except DocumentReadError as exc:
        # Preserve the asynchronous upload contract and create a failed job with
        # the actionable extraction error for the queue to display.
        prepared = exc
    except EmbeddingCreationError as exc:
        prepared = exc

    did, jid = str(uuid.uuid4()), str(uuid.uuid4())
    path = DocumentStorage().save(data)
    try:
        with session_scope() as s:
            doc = Document(
                id=did,
                owner_id=user["id"],
                case_id=case_id,
                collection_id=collection_id,
                title=title or filename,
                document_type=document_type or "Other",
                jurisdiction=jurisdiction or "India",
                filename=filename,
                stored_path=f"uploads/{Path(path).name}",
                content_hash=digest,
                status="queued",
            )
            job = IngestionJob(
                id=jid, owner_id=user["id"], document_id=did, status="queued", progress=0, steps=[], warnings=[]
            )
            s.add_all([doc, job])
            record(s, user["id"], "create", "document", did)
    except Exception:
        object_store().delete(path)
        raise
    pool.submit(process_job, did, jid, user["id"], data, filename, prepared)
    return {
        "document_id": did,
        "job_id": jid,
        "status": "queued",
        "duplicate": False,
        "document": {"id": did, "title": title or filename, "status": "queued"},
    }


@router.get("/admin/storage/status")
def admin_storage_status(user=Depends(require_roles("admin"))):
    settings = get_settings()
    return {
        "backend": settings.object_storage_backend,
        "bucket": settings.supabase_storage_bucket if settings.object_storage_backend == "supabase" else None,
        "ready": settings.object_storage_backend == "supabase",
    }


@router.post("/admin/storage/upload", status_code=202)
async def admin_storage_upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    user=Depends(require_roles("admin")),
):
    if get_settings().object_storage_backend != "supabase":
        raise HTTPException(503, "Supabase Storage is not configured for this workspace")
    return await upload(file=file, title=title, user=user)


@router.get("/admin/storage/knowledge-base")
def admin_storage_knowledge_base(user=Depends(require_roles("admin"))):
    settings = get_settings()
    if settings.object_storage_backend != "supabase":
        raise HTTPException(503, "Supabase Storage is not configured for this workspace")

    from urllib.parse import quote

    from app.supabase_storage import supabase_client

    client = supabase_client()

    def files_in(prefix):
        offset = 0
        files = []
        while True:
            response = client.post(
                f"/storage/v1/object/list/{quote(settings.supabase_storage_bucket, safe='')}",
                json={
                    "prefix": prefix,
                    "limit": 500,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                },
            )
            response.raise_for_status()
            rows = response.json()
            for row in rows:
                name = row.get("name")
                if not name:
                    continue
                if row.get("id") is None and not row.get("metadata"):
                    files.extend(files_in(f"{prefix}{name.strip('/')}/"))
                else:
                    files.append(f"{prefix}{name}")
            if len(rows) < 500:
                break
            offset += 500
        return files

    folder_ids = tuple(ADMIN_KNOWLEDGE_FOLDERS)
    with SessionLocal() as session:
        docs = session.scalars(select(Document).where(Document.source_label.in_(folder_ids))).all()
        doc_ids = [doc.id for doc in docs]
        chunk_counts = dict(
            session.execute(
                select(DocumentChunk.document_id, func.count(DocumentChunk.id))
                .where(DocumentChunk.document_id.in_(doc_ids))
                .group_by(DocumentChunk.document_id)
            ).all()
        ) if doc_ids else {}
        jobs = session.scalars(
            select(IngestionJob).where(IngestionJob.document_id.in_(doc_ids)).order_by(IngestionJob.created_at.desc())
        ).all() if doc_ids else []
        confidence_by_id = {
            doc.id: document_index_confidence(session, doc).get("score") for doc in docs
        }

    latest_jobs = {}
    for job in jobs:
        latest_jobs.setdefault(job.document_id, job)
    docs_by_folder_file = {(doc.source_label, doc.filename): doc for doc in docs}
    folders = []
    for folder_id, label in ADMIN_KNOWLEDGE_FOLDERS.items():
        prefix = f"{folder_id}/"
        keys = files_in(prefix)
        entries = []
        for key in keys:
            filename = key[len(prefix):]
            doc = docs_by_folder_file.get((folder_id, Path(filename).name))
            job = latest_jobs.get(doc.id) if doc else None
            chunks = chunk_counts.get(doc.id, 0) if doc else 0
            confidence = confidence_by_id.get(doc.id) if doc else None
            status = job.status if job else (doc.status if doc else "not_indexed")
            error = job.error if job else None
            if doc and doc.status == "ready" and chunks == 0:
                status = "failed"
                error = error or "No search chunks were created for this file."
            entries.append({
                "filename": filename,
                "status": status,
                "progress": job.progress if job else 0,
                "chunks": chunks,
                "index_confidence": confidence,
                "document_id": doc.id if doc else None,
                "error": error,
                "warnings": job.warnings if job else [],
            })
        folders.append({
            "id": folder_id,
            "label": label,
            "status": "ready" if entries and all(row["status"] == "ready" for row in entries) else (
                "failed" if any(row["status"] == "failed" for row in entries) else "indexing"
            ),
            "file_count": len(entries),
            "indexed_count": sum(row["status"] == "ready" for row in entries),
            "failed_count": sum(row["status"] == "failed" for row in entries),
            "pending_count": sum(row["status"] in {"not_indexed", "queued", "running", "extracting", "indexing"} for row in entries),
            "files": entries,
        })
    return {"bucket": settings.supabase_storage_bucket, "folders": folders}


@router.delete("/admin/storage/knowledge-base/{folder_id}/{filename:path}")
def admin_storage_delete_knowledge_file(folder_id: str, filename: str, user=Depends(require_roles("admin"))):
    settings = get_settings()
    if settings.object_storage_backend != "supabase":
        raise HTTPException(503, "Supabase Storage is not configured for this workspace")
    if folder_id not in ADMIN_KNOWLEDGE_FOLDERS:
        raise HTTPException(404, "Knowledge base folder not found")
    from pathlib import PurePosixPath
    from urllib.parse import quote

    relative = PurePosixPath(filename)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise HTTPException(400, "Invalid storage path")
    source_key = f"{folder_id}/{relative.as_posix()}"
    status = admin_storage_knowledge_base(user)
    folder = next((item for item in status["folders"] if item["id"] == folder_id), None)
    if not folder or relative.as_posix() not in {item["filename"] for item in folder["files"]}:
        raise HTTPException(404, "Stored file not found")

    with SessionLocal() as session:
        indexed = session.scalar(
            select(Document).where(
                Document.source_label == folder_id,
                Document.filename == relative.name,
                Document.visibility == "library",
            )
        )
    if indexed:
        delete_document(indexed.id, user)

    from app.supabase_storage import supabase_client

    response = supabase_client().delete(
        f"/storage/v1/object/{quote(settings.supabase_storage_bucket, safe='')}/{quote(source_key, safe='/')}"
    )
    response.raise_for_status()
    return {"deleted": True, "filename": relative.as_posix(), "document_id": indexed.id if indexed else None}


@router.get("/documents")
def documents(
    q: str | None = None,
    status: str | None = None,
    type: str | None = None,
    case_id: str | None = None,
    collection_id: str | None = None,
    scope: str = Query("all", pattern="^(mine|library|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = "-created_at",
    user=Depends(current_user),
):

    with SessionLocal() as s:
        stmt = select(Document)
        if scope == "mine":
            stmt = stmt.where(Document.owner_id == user["id"])
        elif scope == "library":
            stmt = stmt.where(Document.visibility == "library")
        else:
            stmt = stmt.where(or_(Document.owner_id == user["id"], Document.visibility == "library"))
        if q:
            stmt = stmt.where(Document.title.ilike(f"%{q}%"))
        if status:
            stmt = stmt.where(Document.status == status)
        if type:
            stmt = stmt.where(Document.document_type == type)
        if case_id:
            stmt = stmt.where(Document.case_id == case_id)
        if collection_id:
            stmt = stmt.where(Document.collection_id == collection_id)
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "items": [serialize_document(x, s) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


def get_document(did, user):
    with SessionLocal() as s:
        doc = readable_document(s, did, user)
        if doc is None:
            raise HTTPException(404, "Record not found")
        return doc


def document_index_confidence(session, doc):
    stored = (doc.citation_metadata or {}).get("indexing_confidence")
    if stored:
        return stored
    pages = session.scalars(
        select(DocumentPage).where(DocumentPage.document_id == doc.id).order_by(DocumentPage.page_number)
    ).all()
    if pages:
        return indexing_confidence([
            {
                "page_number": page.page_number,
                "text": page.text,
                "ocr_confidence": page.ocr_confidence,
                "warnings": page.warnings,
            }
            for page in pages
        ])

    # Older library reindexes may have persisted chunks and their source page
    # numbers without creating DocumentPage rows or confidence metadata.
    chunks = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
    ).all()
    if chunks:
        chunks_by_page = {}
        for chunk in chunks:
            page_number = chunk.page_number or 1
            chunks_by_page.setdefault(page_number, []).append(chunk.content or "")
        page_count = max(int(doc.page_count or 0), max(chunks_by_page))
        warnings_by_page = {}
        for warning in doc.warnings or []:
            if isinstance(warning, dict) and warning.get("page"):
                warnings_by_page.setdefault(int(warning["page"]), []).append(warning)
        return indexing_confidence([
            {
                "page_number": page_number,
                # Confidence saturates at 200 words per page, so the fullest
                # chunk gives a stable coverage estimate without double-counting
                # overlapping chunks from long pages.
                "text": max(
                    chunks_by_page.get(page_number, [""]),
                    key=lambda text: len(re.findall(r"\b[\w’'-]+\b", text, flags=re.UNICODE)),
                ),
                "warnings": warnings_by_page.get(page_number, []),
            }
            for page_number in range(1, page_count + 1)
        ])

    if (doc.text_content or "").strip() and (doc.page_count or 1) == 1:
        return indexing_confidence([{"page_number": 1, "text": doc.text_content, "warnings": doc.warnings or []}])
    return indexing_confidence([])


def serialize_document(doc, session=None):
    out = serialize(doc)
    out.pop("stored_path", None)
    out.pop("text_content", None)
    confidence = document_index_confidence(session, doc) if session is not None else (
        (doc.citation_metadata or {}).get("indexing_confidence") or {}
    )
    out["index_confidence"] = confidence.get("score")
    return out


@router.get("/documents/{did}")
def document(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        d = readable_document(s, did, user)
        if d is None:
            raise HTTPException(404, "Record not found")
        return serialize_document(d, s)


@router.patch("/documents/{did}")
def patch_document(did: str, payload: Payload, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    values = payload.model_dump(exclude_unset=True)
    allowed = {"title", "document_type", "jurisdiction", "case_id", "collection_id"}
    if set(values) - allowed:
        raise HTTPException(400, "Only document metadata can be updated")
    if values.get("case_id"):
        with SessionLocal() as s:
            owned(s, Case, values["case_id"], user)
    if values.get("collection_id"):
        from app.models import KnowledgeCollection

        with SessionLocal() as s:
            owned(s, KnowledgeCollection, values["collection_id"], user)
    with session_scope() as s:
        d = owned(s, Document, did, user)
        repo_update(s, d, values)
        record(s, user["id"], "update", "document", did)
        out = serialize(d)
        out.pop("stored_path")
        out.pop("text_content")
        return out


@router.delete("/documents/{did}")
def delete_document(did: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with INDEX_LOCK:
        with session_scope() as s:
            d = owned(s, Document, did, user)
            stored_key = d.stored_path
            chunk_ids = list(s.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == did)))
            s.delete(d)
            record(s, user["id"], "delete", "document", did)
        store().remove(chunk_ids)
    object_store().delete(stored_key)
    return {"deleted": True}


@router.get("/documents/{did}/job")
def doc_job(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        if readable_document(s, did, user) is None:
            raise HTTPException(404, "Record not found")
        j = s.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == did)
            .order_by(IngestionJob.created_at.desc())
        )
        if not j:
            raise HTTPException(404, "Job not found")
        return {
            k: getattr(j, k) for k in ("status", "progress", "steps", "warnings", "pages", "chars", "error")
        }


@router.post("/documents/{did}/retry", status_code=202)
def retry_doc(did: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        d = owned(s, Document, did, user)
        try:
            data = object_store().get(d.stored_path)
        except (ValueError, MissingObject):
            raise HTTPException(404, "Stored upload is unavailable") from None
        jid = str(uuid.uuid4())
        d.status = "queued"
        s.add(
            IngestionJob(id=jid, owner_id=user["id"], document_id=did, status="queued", steps=[], warnings=[])
        )
    pool.submit(process_job, did, jid, user["id"], data, d.filename)
    return {"job_id": jid, "status": "queued"}


@router.get("/documents/{did}/text")
def doc_text(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        doc = readable_document(s, did, user)
        if doc is None:
            raise HTTPException(404, "Record not found")
        return {"text": doc.text_content}


@router.get("/documents/{did}/pages")
def doc_pages(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        if readable_document(s, did, user) is None:
            raise HTTPException(404, "Record not found")
        rows = s.scalars(
            select(DocumentPage).where(DocumentPage.document_id == did).order_by(DocumentPage.page_number)
        ).all()
        pages = []
        for page in rows:
            quality = indexing_confidence([{
                "page_number": page.page_number,
                "text": page.text,
                "ocr_confidence": page.ocr_confidence,
                "warnings": page.warnings,
            }])["pages"][0]
            pages.append({
                "page_number": page.page_number,
                "text": page.text,
                "ocr_confidence": page.ocr_confidence,
                "word_count": quality["word_count"],
                "index_confidence": quality["score"],
                "warnings": page.warnings,
            })
        return {"pages": pages}


def _document_file_response(did: str, user):
    with SessionLocal() as s:
        d = readable_document(s, did, user)
        if d is None:
            raise HTTPException(404, "Record not found")
        stored_key = d.stored_path
        filename = d.filename
    try:
        path = object_store().local_path(stored_key)
    except ValueError:
        path = None
    if not path:
        raise HTTPException(404, "Stored upload is unavailable")
    # FileResponse implements single byte-range requests for local previews.
    return FileResponse(
        path, filename=filename, media_type=mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )


@router.get("/documents/{did}/file", operation_id="get_document_file")
def doc_file(did: str, user=Depends(current_user)):
    return _document_file_response(did, user)


@router.head("/documents/{did}/file", include_in_schema=False)
def doc_file_head(did: str, user=Depends(current_user)):
    return _document_file_response(did, user)


class Review(BaseModel):
    fields: dict[str, object] = Field(default_factory=dict)


def _doc(s, did, user):
    d = get_owned(s, Document, did, user["id"])
    if not d:
        doc = s.get(Document, did)
        if doc is not None:
            from app.routers.domain import assert_library_writable

            assert_library_writable(doc, user)
        raise HTTPException(404, "Document not found")
    return d


@router.get("/documents/{did}/ai-read")
def get_read(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        doc = readable_document(s, did, user)
        if not doc:
            raise HTTPException(404, "Record not found")
        rows = s.scalars(
            select(ExtractionField)
            .where(ExtractionField.document_id == did)
            .order_by(ExtractionField.created_at)
        ).all()
        fields = {
            r.key: {
                "value": r.value,
                "provenance": r.provenance,
                "source": r.source,
                "review_required": r.review_required,
            }
            for r in rows
        }
        return {
            "fields": fields,
            "review_required": any(x["review_required"] for x in fields.values()) if fields else True,
        }


@router.post("/documents/{did}/ai-read")
def run_read(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        d = _doc(s, did, user)
        pages = s.scalars(
            select(DocumentPage).where(DocumentPage.document_id == did).order_by(DocumentPage.page_number)
        ).all()
        candidate = None
        for page in pages:
            m = re.search(
                r".{0,180}(?:arbitration agreement|refer(?:red)? to arbitration|arbitrator).{0,260}",
                page.text,
                re.I | re.S,
            )
            if m:
                candidate = {"found": True, "quote": m.group(0).strip(), "page": page.page_number}
                break
        page_texts = [f"[Page {p.page_number}] {p.text}" for p in pages]
        source_text = "\n\n".join(page_texts)
        truncated = len(source_text) > 12000
        source_text = source_text[:12000]
        preference = s.scalar(
            select(AppPreference).where(AppPreference.owner_id == user["id"], AppPreference.key == "ai")
        )
        ai_settings = preference.value if preference else {}
    keys = {
        "parties": [], "key_dates": [], "contract_references": [],
        "arbitration_clause": {"found": False, "quote": None, "page": None},
        "jurisdiction": None, "governing_law": None, "key_provisions": [],
        "possible_legal_issues": [], "summary": "",
    }
    if not pages:
        keys["jurisdiction"] = d.jurisdiction
        keys["summary"] = (d.text_content or "")[:700]
    prompt = (
        "Extract only facts explicitly evidenced in the document. Return one JSON object with exactly these keys: "
        "parties (list of {name, role}), key_dates (list of {date, description}), "
        "contract_references (list of strings), arbitration_clause ({found, quote, page}), "
        "jurisdiction, governing_law, key_provisions (list of strings), "
        "possible_legal_issues (list of strings), summary (string). Use null/empty values when absent. "
        f"The input was truncated: {str(truncated).lower()}. Do not infer missing details.\n\nDOCUMENT:\n{source_text}"
    )
    from app.main import configured_llm_model, llm_answer

    effective_model = configured_llm_model(ai_settings.get("model"))
    llm_text = llm_answer(
        prompt,
        [],
        base_url=ai_settings.get("base_url"),
        model=ai_settings.get("model"),
        json_mode=True,
    )
    model = effective_model if llm_text else None
    if llm_text:
        import json

        cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", llm_text.strip(), flags=re.I)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                for key, fallback in keys.items():
                    value = parsed.get(key)
                    if isinstance(fallback, list):
                        if isinstance(value, list):
                            if key == "parties":
                                value = [
                                    {"name": item.get("name", ""), "role": item.get("role", "")}
                                    for item in value if isinstance(item, dict)
                                ]
                            elif key == "key_dates":
                                value = [
                                    {"date": item.get("date", ""), "description": item.get("description", "")}
                                    for item in value if isinstance(item, dict)
                                ]
                            else:
                                value = [item for item in value if isinstance(item, str)]
                            keys[key] = value
                    elif key == "arbitration_clause" and isinstance(value, dict):
                        if isinstance(value.get("found"), bool):
                            keys[key] = {
                                "found": value["found"],
                                "quote": value.get("quote") if isinstance(value.get("quote"), str) else None,
                                "page": value.get("page") if isinstance(value.get("page"), int) else None,
                            }
                    elif key in {"jurisdiction", "governing_law", "summary"}:
                        if isinstance(value, str):
                            keys[key] = value
                        elif value is None:
                            keys[key] = None if key != "summary" else ""
        except (ValueError, TypeError):
            pass
    else:
        keys["jurisdiction"] = d.jurisdiction
        keys["summary"] = (d.text_content or "")[:700]
    if not keys["arbitration_clause"].get("quote") and candidate:
        keys["arbitration_clause"] = candidate
    values = keys
    source = (
        f"{get_settings().ai_provider}:{effective_model}"
        if model
        else "Local text extraction; candidate only"
    )
    with session_scope() as s:
        _doc(s, did, user)
        for key, value in values.items():
            s.add(
                ExtractionField(
                    id=str(uuid.uuid4()),
                    owner_id=user["id"],
                    document_id=did,
                    key=key,
                    value=value,
                    provenance="ai_suggested",
                    source=source,
                    review_required=True,
                )
            )
        record(s, user["id"], "generate", "ai_read", did)
    return {
        "status": "model_generated" if model else "local_extraction",
        "model": model,
        "fields": {
            k: {
                "value": v,
                "provenance": "ai_suggested",
                "source": source,
                "review_required": True,
            }
            for k, v in values.items()
        },
        "review_required": True,
    }


@router.patch("/documents/{did}/extraction")
def review(did: str, payload: Review, user=Depends(current_user)):
    with session_scope() as s:
        _doc(s, did, user)
        rows = []
        for key, value in payload.fields.items():
            row = ExtractionField(
                id=str(uuid.uuid4()),
                owner_id=user["id"],
                document_id=did,
                key=key,
                value=value,
                provenance="extracted_reviewed",
                source="User reviewed",
                review_required=False,
            )
            s.add(row)
            rows.append(row)
        record(s, user["id"], "update", "extraction_fields", did, {"fields": list(payload.fields)})
        return {
            "fields": {
                r.key: {
                    "value": r.value,
                    "provenance": r.provenance,
                    "source": r.source,
                    "review_required": False,
                }
                for r in rows
            },
            "review_required": False,
        }
