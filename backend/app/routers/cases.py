"""Case relationships and event timeline endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.db import SessionLocal, session_scope
from app.models import *
from app.repositories.domain import create as repo_create
from app.repositories.domain import list_owned, serialize
from app.repositories.domain import update as repo_update
from app.routers.domain import add_derived_fields, owned
from app.security import current_user
from app.services.audit import record

router = APIRouter(prefix="/api/v1", tags=["cases"])


class Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


@router.get("/clients/{cid}/cases")
def client_cases(cid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        owned(s, Client, cid, user)
        return list_owned(s, Case, user["id"], page=1, page_size=100, extra_filters=(Case.client_id == cid,))


@router.get("/cases/{cid}/overview")
def case_overview(cid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        case = owned(s, Case, cid, user)
        out = serialize(case)
        add_derived_fields(s, Case, out, user["id"])
        for key, cls in (("participants", CaseParticipant), ("tasks", Task), ("hearings", Hearing)):
            out[key] = list_owned(s, cls, user["id"], case_id=cid, page=1, page_size=100)["items"]
        out["documents_count"] = (
            s.scalar(
                select(func.count(Document.id)).where(
                    Document.owner_id == user["id"], Document.case_id == cid
                )
            )
            or 0
        )
        out["drafts_count"] = (
            s.scalar(select(func.count(Draft.id)).where(Draft.owner_id == user["id"], Draft.case_id == cid))
            or 0
        )
        return out


# Case participants and timeline use their own typed tables.
@router.post("/cases/{cid}/participants")
def add_participant(cid: str, payload: Payload, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    data = payload.model_dump(exclude_unset=True)
    with session_scope() as s:
        owned(s, Case, cid, user)
        row = repo_create(s, CaseParticipant, user["id"], data, case_id=cid)
        record(s, user["id"], "create", "case_participant", row.id)
        return serialize(row)


@router.patch("/cases/{cid}/participants/{pid}")
def update_participant(cid: str, pid: str, payload: Payload, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        row = owned(s, CaseParticipant, pid, user)
        if row.case_id != cid:
            raise HTTPException(404, "Participant not found")
        repo_update(s, row, payload.model_dump(exclude_unset=True))
        return serialize(row)


@router.delete("/cases/{cid}/participants/{pid}")
def delete_participant(cid: str, pid: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        row = owned(s, CaseParticipant, pid, user)
        if row.case_id != cid:
            raise HTTPException(404, "Participant not found")
        s.delete(row)
        return {"deleted": True}


@router.get("/cases/{cid}/events")
def case_events(
    cid: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user)
):
    with SessionLocal() as s:
        owned(s, Case, cid, user)
        return list_owned(s, CaseEvent, user["id"], case_id=cid, page=page, page_size=page_size)


@router.get("/cases/{cid}/events/{eid}")
def get_case_event(cid: str, eid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        row = owned(s, CaseEvent, eid, user)
        if row.case_id != cid:
            raise HTTPException(404, "Case event not found")
        return serialize(row)


@router.patch("/cases/{cid}/events/{eid}")
def patch_case_event(cid: str, eid: str, payload: Payload, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        row = owned(s, CaseEvent, eid, user)
        if row.case_id != cid:
            raise HTTPException(404, "Case event not found")
        repo_update(s, row, payload.model_dump(exclude_unset=True))
        record(s, user["id"], "update", "case_event", eid)
        return serialize(row)


@router.delete("/cases/{cid}/events/{eid}")
def delete_case_event(cid: str, eid: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        row = owned(s, CaseEvent, eid, user)
        if row.case_id != cid:
            raise HTTPException(404, "Case event not found")
        s.delete(row)
        record(s, user["id"], "delete", "case_event", eid)
        return {"deleted": True}


@router.post("/cases/{cid}/events")
def add_case_event(cid: str, payload: Payload, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        owned(s, Case, cid, user)
        row = repo_create(s, CaseEvent, user["id"], payload.model_dump(exclude_unset=True), case_id=cid)
        record(s, user["id"], "create", "case_event", row.id)
        return serialize(row)
