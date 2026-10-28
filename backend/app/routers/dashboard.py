"""Database-backed dashboard and calendar endpoints."""

from datetime import datetime, time, timedelta
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, Case, CaseEvent, Document, Draft, Hearing, Task
from app.security import current_user
from app.timezone import to_utc_iso, to_workspace_iso, to_workspace_naive, workspace_now

router = APIRouter(prefix="/api/v1", tags=["dashboard", "calendar"])


def _case_event_title(event: CaseEvent) -> str:
    detail = (event.detail or "").strip()
    normalized_type = event.type.replace("_", " ").strip().casefold()
    if detail and detail.casefold() not in {event.type.casefold(), normalized_type}:
        return detail
    return normalized_type[:1].upper() + normalized_type[1:] if normalized_type else "Case event"


def _case_event_item(event: CaseEvent, case_titles: dict[str, str]) -> dict:
    title = _case_event_title(event)
    detail = (event.detail or "").strip()
    if not detail or detail.casefold() in {event.type.casefold(), event.type.replace("_", " ").casefold()}:
        detail = title
    return {
        "id": event.id,
        "type": "event",
        "event_type": event.type,
        "title": title,
        "detail": detail,
        "case_id": event.case_id,
        "case_title": case_titles.get(event.case_id),
        "at": to_workspace_iso(event.occurred_at),
        "all_day": event.occurred_at.time() == time.min,
    }


@router.get("/dashboard/summary")
def dashboard(user=Depends(current_user)):
    today = workspace_now().date()
    week = datetime.combine(today + timedelta(days=7), datetime.min.time())
    with SessionLocal() as s:

        def cnt(cls, *criteria):
            return (
                s.scalar(select(func.count()).select_from(cls).where(cls.owner_id == user["id"], *criteria))
                or 0
            )

        return {
            "greeting": "Good day",
            "first_name": user["name"].split()[0],
            "today": today.isoformat(),
            "active_cases": cnt(Case, Case.status == "active"),
            "pending_arbitrations": cnt(Case, Case.status == "pending"),
            "hearings_this_week": cnt(
                Hearing, Hearing.at >= datetime.combine(today, datetime.min.time()), Hearing.at < week
            ),
            "documents_processed": cnt(Document, Document.status == "ready"),
            "drafts_in_progress": cnt(Draft, Draft.status != "done"),
            "tasks_due": cnt(Task, Task.status != "done", Task.due_at <= week),
            "tasks_overdue": cnt(
                Task, Task.status != "done", Task.due_at < datetime.combine(today, datetime.min.time())
            ),
        }


@router.get("/dashboard/activity")
def activity(user=Depends(current_user)):
    with SessionLocal() as s:
        rows = s.scalars(
            select(AuditEvent)
            .where(AuditEvent.owner_id == user["id"])
            .order_by(AuditEvent.created_at.desc())
            .limit(20)
        ).all()
    return [
        {
            "id": r.id,
            "type": r.action,
            "actor": user["name"],
            "title": f"{r.action.title()} {r.object_type}",
            "case_id": None,
            "at": to_utc_iso(r.created_at),
        }
        for r in rows
    ]


@router.get("/dashboard/upcoming")
def upcoming(days: int = Query(30, ge=1, le=365), user=Depends(current_user)):
    now = workspace_now()
    today = now.date()
    start = now.replace(tzinfo=None)
    end = start + timedelta(days=days)
    with SessionLocal() as s:
        hs = s.scalars(
            select(Hearing).where(Hearing.owner_id == user["id"], Hearing.at >= start, Hearing.at <= end)
        ).all()
        ts = s.scalars(
            select(Task).where(
                Task.owner_id == user["id"], Task.due_at >= start, Task.due_at <= end, Task.status != "done"
            )
        ).all()
        events = s.scalars(
            select(CaseEvent).where(
                CaseEvent.owner_id == user["id"], CaseEvent.occurred_at >= start, CaseEvent.occurred_at <= end
            )
        ).all()
        cases = s.scalars(select(Case).where(Case.owner_id == user["id"])).all()
        case_titles = {case.id: case.title for case in cases}
        out = (
            [
                {
                    "id": x.id,
                    "type": "hearing",
                    "title": x.title,
                    "case_id": x.case_id,
                    "case_title": case_titles.get(x.case_id),
                    "at": to_workspace_iso(x.at),
                    "due_in_days": (x.at.date() - today).days,
                }
                for x in hs
            ]
            + [
                {
                    "id": x.id,
                    "type": "deadline",
                    "title": x.title,
                    "case_id": x.case_id,
                    "case_title": case_titles.get(x.case_id),
                    "at": to_workspace_iso(x.due_at),
                    "due_in_days": (x.due_at.date() - today).days,
                }
                for x in ts
                if x.due_at
            ]
            + [
                {
                    **_case_event_item(x, case_titles),
                    "due_in_days": (x.occurred_at.date() - today).days,
                }
                for x in events
            ]
        )
        for case in cases:
            for field, label in (
                ("filed_at", "Filing date"),
                ("notice_date", "Notice date"),
                ("limitation_date", "Limitation date"),
            ):
                at = getattr(case, field)
                if at and start <= at <= end:
                    out.append(
                        {
                            "id": f"{case.id}:{field}",
                            "type": "event" if field == "filed_at" else "deadline",
                            "title": label,
                            "case_id": case.id,
                            "case_title": case.title,
                            "at": to_workspace_iso(at),
                            "all_day": at.time() == time.min,
                            "due_in_days": (at.date() - today).days,
                        }
                    )
    return sorted(out, key=lambda x: x["at"])


@router.get("/calendar")
def calendar(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    envelope: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    user=Depends(current_user),
):
    """Return the legacy bare list by default; `envelope=true` opts into pagination metadata."""
    start = to_workspace_naive(from_) if from_ else datetime.min
    end = to_workspace_naive(to) if to else datetime.max
    with SessionLocal() as s:
        hs = s.scalars(
            select(Hearing).where(Hearing.owner_id == user["id"], Hearing.at >= start, Hearing.at <= end)
        ).all()
        tasks = s.scalars(
            select(Task).where(Task.owner_id == user["id"], Task.due_at >= start, Task.due_at <= end)
        ).all()
        events = s.scalars(
            select(CaseEvent).where(
                CaseEvent.owner_id == user["id"], CaseEvent.occurred_at >= start, CaseEvent.occurred_at <= end
            )
        ).all()
        cases = s.scalars(select(Case).where(Case.owner_id == user["id"])).all()
        case_titles = {case.id: case.title for case in cases}
    items = (
        [
            {
                "id": x.id,
                "type": "hearing",
                "title": x.title,
                "case_id": x.case_id,
                "case_title": case_titles.get(x.case_id),
                "at": to_workspace_iso(x.at),
            }
            for x in hs
        ]
        + [
            {
                "id": x.id,
                "type": "deadline",
                "title": x.title,
                "case_id": x.case_id,
                "case_title": case_titles.get(x.case_id),
                "at": to_workspace_iso(x.due_at),
            }
            for x in tasks
            if x.due_at
        ]
        + [_case_event_item(x, case_titles) for x in events]
    )
    for case in cases:
        for field, label in (
            ("filed_at", "Filing date"),
            ("notice_date", "Notice date"),
            ("limitation_date", "Limitation date"),
        ):
            at = getattr(case, field)
            if at and start <= at <= end:
                items.append(
                    {
                        "id": f"{case.id}:{field}",
                        "type": "event" if field == "filed_at" else "deadline",
                        "title": label,
                        "case_id": case.id,
                        "case_title": case.title,
                        "at": to_workspace_iso(at),
                        "all_day": at.time() == time.min,
                    }
                )
    ordered = sorted(items, key=lambda x: x["at"])
    if envelope:
        total = len(ordered)
        return {
            "items": ordered[(page - 1) * page_size : page * page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": ceil(total / page_size) if total else 0,
        }
    return ordered
