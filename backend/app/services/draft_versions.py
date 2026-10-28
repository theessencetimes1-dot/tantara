"""Shared persistence helpers for immutable draft history snapshots."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Draft, DraftVersion


def snapshot_draft(session: Session, draft: Draft, content: str, change_note: str | None):
    """Store a draft state with the next per-draft version number."""
    latest = (
        session.scalar(
            select(func.max(DraftVersion.version_number)).where(
                DraftVersion.draft_id == draft.id,
                DraftVersion.owner_id == draft.owner_id,
            )
        )
        or 0
    )
    version = DraftVersion(
        id=str(uuid.uuid4()),
        owner_id=draft.owner_id,
        draft_id=draft.id,
        version_number=latest + 1,
        content_markdown=content,
        change_note=change_note,
    )
    session.add(version)
    session.flush()
    return version
