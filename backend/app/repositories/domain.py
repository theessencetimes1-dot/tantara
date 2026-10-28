"""Typed domain repository helpers; filtering and pagination execute in SQL."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models
from app.timezone import to_utc_iso, to_workspace_iso, to_workspace_naive

ENTITY_MODELS = {
    "clients": models.Client,
    "cases": models.Case,
    "hearings": models.Hearing,
    "tasks": models.Task,
    "drafts": models.Draft,
    "bundles": models.FilingBundle,
    "notes": models.Note,
    "community/posts": models.CommunityPost,
}


def fields_for(cls):
    return {c.key for c in cls.__table__.columns}


def serialize(row):
    if row is None:
        return None
    return {
        k: (
            to_utc_iso(value)
            if isinstance((value := getattr(row, k)), datetime) and k in {"created_at", "updated_at"}
            else to_workspace_iso(value)
            if isinstance(value, datetime)
            else value
        )
        for k in fields_for(type(row))
    }


def get_owned(session: Session, cls, record_id: str, owner_id: str):
    return session.scalar(select(cls).where(cls.id == record_id, cls.owner_id == owner_id))


def list_owned(
    session: Session,
    cls,
    owner_id: str,
    *,
    q=None,
    status=None,
    case_id=None,
    page=1,
    page_size=20,
    sort="created_at",
    extra_filters=(),
    include_workspace=False,
):
    if include_workspace and cls is models.CommunityPost:
        stmt = select(cls).where(or_(cls.owner_id == owner_id, cls.visibility == "workspace"))
    else:
        stmt = select(cls).where(cls.owner_id == owner_id)
    if case_id and hasattr(cls, "case_id"):
        stmt = stmt.where(cls.case_id == case_id)
    if status and hasattr(cls, "status"):
        stmt = stmt.where(cls.status == status)
    if q:
        terms = [
            getattr(cls, k).ilike(f"%{q}%")
            for k in ("title", "name", "reference_number", "organization", "body")
            if hasattr(cls, k)
        ]
        if terms:
            stmt = stmt.where(or_(*terms))
    for clause in extra_filters:
        stmt = stmt.where(clause)
    valid = {c.key for c in cls.__table__.columns}
    key = sort.removeprefix("-")
    if key not in valid:
        key = "created_at"
    column = getattr(cls, key)
    stmt = stmt.order_by(column.desc() if sort.startswith("-") else column.asc())
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [serialize(x) for x in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


def _coerce(cls, key, value):
    if value is None:
        return None
    typ = cls.__table__.columns[key].type
    if typ.__class__.__name__ == "DateTime":
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if isinstance(parsed, datetime):
            return to_workspace_naive(parsed)
    if typ.__class__.__name__ == "Date" and isinstance(value, str):
        return date.fromisoformat(value[:10])
    if typ.__class__.__name__ in {"Numeric", "Float"}:
        return Decimal(str(value)) if typ.__class__.__name__ == "Numeric" else float(value)
    return value


def create(session: Session, cls, owner_id: str, values: dict, **extra):
    allowed = fields_for(cls) - {"id", "created_at", "updated_at", "owner_id", "is_demo"}
    data = {k: _coerce(cls, k, v) for k, v in values.items() if k in allowed}
    obj = cls(id=str(uuid.uuid4()), owner_id=owner_id, **data, **extra)
    session.add(obj)
    session.flush()
    return obj


def update(session: Session, obj, values: dict):
    allowed = fields_for(type(obj)) - {"id", "created_at", "updated_at", "owner_id", "is_demo"}
    for key, value in values.items():
        if key in allowed:
            setattr(obj, key, _coerce(type(obj), key, value))
    session.flush()
    return obj
