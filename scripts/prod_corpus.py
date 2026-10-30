#!/usr/bin/env python3
"""Publish the reference-law corpus into the production Supabase workspace.

Everything here is the product's own ingestion path — the same
``DocumentStorage`` → ``process_job`` pipeline an upload takes through the HTTP
API — so the production workspace is built the way it will be maintained.
These documents are statute texts from public sources, so they are written with
``visibility="library"`` and are readable by every account. Client uploads stay
private; this script is the only path that publishes.

Run it inside the production image so the baked FastEmbed model is used:

    podman run --rm --env-file /tmp/prod-corpus.env \
        localhost/tantara-backend-prod:<tag> \
        python /app/scripts/prod_corpus.py /app/legal_docs
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from prod_db import configure_environment  # noqa: E402

ACCEPTED = {".pdf", ".docx", ".txt", ".md"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", default="legal_docs")
    parser.add_argument("--email", default="library@theessencetimes.com")
    parser.add_argument("--jurisdiction", default="India")
    parser.add_argument("--document-type", default="statute")
    args = parser.parse_args()

    configure_environment()
    from app.db import SessionLocal, session_scope
    from app.ingestion import DocumentStorage
    from app.models import Document, DocumentChunk, IngestionJob, User
    from app.object_store import ensure_bucket
    from app.routers.documents import process_job
    from app.security import hash_password
    from sqlalchemy import func, select

    bucket = ensure_bucket()
    print(f"object storage bucket ready: {bucket or 'filesystem'}")

    with session_scope() as session:
        owner = session.scalar(select(User).where(User.email == args.email))
        if owner is None:
            from prod_env import production_password

            password = os.environ.get("TANTARA_CORPUS_PASSWORD") or production_password()
            owner = User(
                id=str(uuid.uuid4()),
                name="Tantra Reference Library",
                email=args.email,
                password_hash=hash_password(password),
                role="advocate",
                avatar_initials="RL",
                title="Reference librarian",
            )
            session.add(owner)
            session.commit()
            print(f"created the corpus owner account {args.email}")
        owner_id = owner.id

    folder = Path(args.folder)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in ACCEPTED)
    if not files:
        print(f"no documents found in {folder}", file=sys.stderr)
        return 1

    failures = 0
    for path in files:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        with SessionLocal() as session:
            existing = session.scalar(
                select(Document).where(Document.owner_id == owner_id, Document.content_hash == digest)
            )
            if existing is not None:
                print(f"{path.name:58} already indexed as {existing.id[:8]} ({existing.status})")
                continue
        doc_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        stored = DocumentStorage().save(data)
        with session_scope() as session:
            session.add(
                Document(
                    id=doc_id,
                    owner_id=owner_id,
                    title=path.stem[:180],
                    document_type=args.document_type,
                    jurisdiction=args.jurisdiction,
                    filename=path.name[:180],
                    stored_path=stored,
                    content_hash=digest,
                    # Public-source statute text: shared with every account.
                    visibility="library",
                    status="queued",
                )
            )
            session.add(
                IngestionJob(
                    id=job_id,
                    owner_id=owner_id,
                    document_id=doc_id,
                    status="queued",
                    steps=[],
                    warnings=[],
                )
            )
        process_job(doc_id, job_id, owner_id, data, path.name)
        with SessionLocal() as session:
            doc = session.get(Document, doc_id)
            pages = doc.page_count if doc else 0
            chunks = (
                session.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc_id))
                or 0
            )
            status = doc.status if doc else "failed"
        flag = "" if status == "ready" else "  <-- FAILED"
        failures += status != "ready"
        print(f"{path.name:58} {status:8} pages={pages:4} chunks={chunks:5}{flag}")

    with SessionLocal() as session:
        library = session.scalar(
            select(Document).where(Document.owner_id == owner_id, Document.visibility == "library")
        )
        total = session.scalar(select(Document).where(Document.owner_id == owner_id))
    print(f"library rows for {args.email}: {total} (first id {library.id[:8] if library else '—'})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
