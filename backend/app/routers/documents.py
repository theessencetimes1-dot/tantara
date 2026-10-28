"""Page-aware upload, async ingestion, file access, and AI Read routes."""

import hashlib
import logging
import mimetypes
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.chunking import chunk_text
from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.embeddings import embed_documents
from app.ingestion import DocumentExtractor, DocumentStorage
from app.models import Case, Document, DocumentChunk, DocumentPage, ExtractionField, IngestionJob
from app.repositories.domain import get_owned, serialize
from app.repositories.domain import update as repo_update
from app.routers.domain import owned
from app.security import current_user
from app.services.audit import record
from app.services.vector_store import INDEX_LOCK, store
from app.storage_paths import stored_path

router = APIRouter(prefix="/api/v1", tags=["documents"])


class Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tantara-ingest")


def _job_update(job_id, **values):
    with session_scope() as s:
        job = s.get(IngestionJob, job_id)
        if job:
            for k, v in values.items():
                setattr(job, k, v)


def process_job(doc_id, job_id, owner_id, data, filename):
    pages = []
    warnings = []
    try:
        _job_update(
            job_id,
            status="extracting",
            progress=10,
            steps=[{"key": "extract", "label": "Extracting pages", "state": "active"}],
        )
        pages, warnings = DocumentExtractor().extract(filename, data)
        all_text = "\n".join(p["text"] for p in pages)
        if not all_text.strip():
            raise ValueError("No text could be extracted")
        chunks = []
        offset = 0
        for p in pages:
            for ch in chunk_text(
                p["text"], get_settings().chunk_size_chars, get_settings().chunk_overlap_chars
            ):
                chunks.append(
                    {
                        **ch,
                        "page_number": p["page_number"],
                        "start_char": ch["start_char"] + offset,
                        "end_char": ch["end_char"] + offset,
                    }
                )
            offset += len(p["text"]) + 1
        vectors = embed_documents([x["content"] for x in chunks])
        _job_update(
            job_id,
            status="indexing",
            progress=75,
            steps=[
                {"key": "extract", "label": "Extracting pages", "state": "complete"},
                {"key": "embed", "label": "Creating local embeddings", "state": "complete"},
                {"key": "index", "label": "Writing search index", "state": "active"},
            ],
        )
        indexed = []
        with INDEX_LOCK:
            with session_scope() as s:
                doc = s.get(Document, doc_id)
                doc.text_content = all_text
                doc.page_count = len(pages)
                doc.warnings = warnings
                doc.status = "ready"
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
            store().add(indexed)
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
        logging.warning("Document processing failed (%s)", type(exc).__name__)
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
        _job_update(
            job_id,
            status="failed",
            progress=0,
            error=f"{type(exc).__name__}: processing failed",
            warnings=warnings,
        )


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
            select(Document).where(Document.owner_id == user["id"], Document.content_hash == digest)
        )
    if old:
        raise HTTPException(
            409, {"message": "Duplicate document", "existing_document": {"id": old.id, "title": old.title}}
        )
    did, jid = str(uuid.uuid4()), str(uuid.uuid4())
    path = DocumentStorage().save(data)
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
    pool.submit(process_job, did, jid, user["id"], data, filename)
    return {
        "document_id": did,
        "job_id": jid,
        "status": "queued",
        "duplicate": False,
        "document": {"id": did, "title": title or filename, "status": "queued"},
    }


@router.get("/documents")
def documents(
    q: str | None = None,
    status: str | None = None,
    type: str | None = None,
    case_id: str | None = None,
    collection_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = "-created_at",
    user=Depends(current_user),
):

    with SessionLocal() as s:
        stmt = select(Document).where(Document.owner_id == user["id"])
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
            "items": [
                {k: v for k, v in serialize(x).items() if k not in {"stored_path", "text_content"}}
                for x in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


def get_document(did, user):
    with SessionLocal() as s:
        return owned(s, Document, did, user)


@router.get("/documents/{did}")
def document(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        d = owned(s, Document, did, user)
        out = serialize(d)
        out.pop("stored_path")
        out.pop("text_content")
        return out


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
            path = stored_path("uploads", d.stored_path)
            chunk_ids = list(s.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == did)))
            s.delete(d)
            record(s, user["id"], "delete", "document", did)
        store().remove(chunk_ids)
    if path:
        path.unlink(missing_ok=True)
    return {"deleted": True}


@router.get("/documents/{did}/job")
def doc_job(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        owned(s, Document, did, user)
        j = s.scalar(
            select(IngestionJob)
            .where(IngestionJob.document_id == did, IngestionJob.owner_id == user["id"])
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
            path = stored_path("uploads", d.stored_path)
        except ValueError:
            raise HTTPException(404, "Stored upload is unavailable") from None
        if not path.is_file():
            raise HTTPException(404, "Stored upload is unavailable")
        data = path.read_bytes()
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
        return {"text": owned(s, Document, did, user).text_content}


@router.get("/documents/{did}/pages")
def doc_pages(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        owned(s, Document, did, user)
        rows = s.scalars(
            select(DocumentPage).where(DocumentPage.document_id == did).order_by(DocumentPage.page_number)
        ).all()
        return {
            "pages": [
                {
                    "page_number": p.page_number,
                    "text": p.text,
                    "ocr_confidence": p.ocr_confidence,
                    "warnings": p.warnings,
                }
                for p in rows
            ]
        }


def _document_file_response(did: str, user):
    with SessionLocal() as s:
        d = owned(s, Document, did, user)
        try:
            path = stored_path("uploads", d.stored_path)
        except ValueError:
            raise HTTPException(404, "Stored upload is unavailable") from None
        filename = d.filename
    if not path.is_file():
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
        raise HTTPException(404, "Document not found")
    return d


@router.get("/documents/{did}/ai-read")
def get_read(did: str, user=Depends(current_user)):
    with SessionLocal() as s:
        _doc(s, did, user)
        rows = s.scalars(
            select(ExtractionField)
            .where(ExtractionField.document_id == did, ExtractionField.owner_id == user["id"])
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
        values = {
            "document_type": d.document_type,
            "parties": [],
            "key_dates": [],
            "contract_references": [],
            "arbitration_clause": candidate or {"found": False, "quote": None, "page": None},
            "jurisdiction": d.jurisdiction,
            "governing_law": None,
            "key_provisions": [],
            "possible_legal_issues": [],
            "summary": (d.text_content[:700] if d.text_content else ""),
        }
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
                    source="Local text extraction; candidate only",
                    review_required=True,
                )
            )
        record(s, user["id"], "generate", "ai_read", did)
    return {
        "status": "local_extraction",
        "model": None,
        "fields": {
            k: {
                "value": v,
                "provenance": "ai_suggested",
                "source": "Local text extraction; candidate only",
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
