"""Structured audit writes without content or credential logging."""

import uuid

from app.models import AuditEvent


def record(session, actor_id, action, object_type, object_id, details=None):
    session.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            owner_id=actor_id,
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
        )
    )
