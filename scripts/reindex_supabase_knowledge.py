#!/usr/bin/env python3
"""Rebuild the indexed library from the three admin managed Supabase folders.

Run from the repository root with the production credentials available to
``scripts/prod_db.py``. Objects are read from Supabase Storage, then passed
through the same durable storage and ingestion pipeline as normal uploads.
"""

from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from prod_db import configure_environment  # noqa: E402

FOLDERS = (
    ("01_INDIAN_PRIMARY_ACTS", "statute"),
    ("02_AMENDMENTS_AND_NOTIFICATIONS", "statute"),
    ("03_ARBITRATION_RULES_AND_REFERENCE", "reference"),
)
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}
OWNER_EMAIL = "library@theessencetimes.com"


def main() -> int:
    configure_environment()

    from sqlalchemy import func, select

    from app.config import get_settings
    from app.db import SessionLocal, session_scope
    from app.ingestion import DocumentStorage
    from app.models import Document, DocumentChunk, IngestionJob, User
    from app.object_store import ensure_bucket
    from app.routers.documents import process_job
    from app.supabase_storage import supabase_client

    settings = get_settings()
    bucket = ensure_bucket()
    client = supabase_client()
    with SessionLocal() as session:
        owner = session.scalar(select(User).where(User.email == OWNER_EMAIL))
        if owner is None:
            raise SystemExit(f"Corpus owner account not found: {OWNER_EMAIL}")
        owner_id = owner.id

    failures = 0
    seen_hashes = {}
    for folder_id, document_type in FOLDERS:
        prefix = f"{folder_id}/"
        listing = client.post(
            f"/storage/v1/object/list/{quote(bucket, safe='')}",
            json={"prefix": prefix, "limit": 500, "offset": 0, "sortBy": {"column": "name", "order": "asc"}},
        )
        listing.raise_for_status()
        rows = listing.json()
        files = [row for row in rows if row.get("name") and (row.get("id") is not None or row.get("metadata"))]
        for row in files:
            filename = Path(row["name"]).name
            if Path(filename).suffix.lower() not in SUPPORTED:
                print(f"SKIP {folder_id}/{filename}: unsupported type")
                continue
            object_path = f"{prefix}{row['name']}"
            response = client.get(
                f"/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
            )
            response.raise_for_status()
            data = response.content
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen_hashes:
                doc_id = seen_hashes[digest]
                print(f"DUPLICATE {folder_id}/{filename}: same content as an earlier folder object ({doc_id[:8]})")
                continue
            seen_hashes[digest] = "pending"

            with SessionLocal() as session:
                doc = session.scalar(
                    select(Document)
                    .where(Document.content_hash == digest, Document.visibility == "library")
                    .order_by((Document.owner_id == owner_id).desc())
                )
                if doc is not None:
                    doc_id = doc.id
                    doc_owner_id = doc.owner_id
                    doc.title = Path(filename).stem[:180]
                    doc.filename = filename[:180]
                    doc.source_label = folder_id
                    doc.status = "queued"
                    doc.stored_path = DocumentStorage().save(data)
                else:
                    doc_id = str(uuid.uuid4())
                    doc_owner_id = owner_id
                    stored_path = DocumentStorage().save(data)
                    doc = Document(
                        id=doc_id,
                        owner_id=doc_owner_id,
                        title=Path(filename).stem[:180],
                        document_type=document_type,
                        jurisdiction="India" if folder_id != "03_ARBITRATION_RULES_AND_REFERENCE" else "International",
                        source_label=folder_id,
                        filename=filename[:180],
                        stored_path=stored_path,
                        content_hash=digest,
                        visibility="library",
                        status="queued",
                    )
                    session.add(doc)
                job_id = str(uuid.uuid4())
                session.add(
                    IngestionJob(
                        id=job_id,
                        owner_id=doc_owner_id,
                        document_id=doc_id,
                        status="queued",
                        progress=0,
                        steps=[],
                        warnings=[],
                    )
                )
                session.commit()

            process_job(doc_id, job_id, doc_owner_id, data, filename)
            with SessionLocal() as session:
                final_doc = session.get(Document, doc_id)
                final_job = session.get(IngestionJob, job_id)
                status = final_job.status if final_job else (final_doc.status if final_doc else "missing")
                pages = final_job.pages if final_job else 0
                chunks = (
                    session.scalar(
                        select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id)
                    )
                    or 0
                ) if final_doc else 0
                error = final_job.error if final_job else None
            if status == "ready":
                seen_hashes[digest] = doc_id
                print(f"READY {folder_id}/{filename}: pages={pages} chunks={chunks}")
            else:
                failures += 1
                print(f"FAILED {folder_id}/{filename}: {error or status}")

    print(f"Reindex complete from {bucket}: {len(seen_hashes)} unique files; failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
