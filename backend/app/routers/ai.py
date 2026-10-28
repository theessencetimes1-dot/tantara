"""Typed AI research session history and saved research items."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import SessionLocal, session_scope
from app.models import Citation, CommunityPost, ResearchMessage, ResearchSession, SavedItem
from app.repositories.domain import get_owned, serialize
from app.security import current_user

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class SessionBody(BaseModel):
    title: str = Field(default="New research session", max_length=300)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=8000)


class SavedBody(BaseModel):
    item_type: str
    item_id: str


@router.get("/sessions")
def sessions(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user)
):
    with SessionLocal() as s:
        stmt = select(ResearchSession).where(ResearchSession.owner_id == user["id"])
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(ResearchSession.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "items": [serialize(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


@router.post("/sessions")
def create_session(payload: SessionBody, user=Depends(current_user)):
    with session_scope() as s:
        row = ResearchSession(id=str(uuid.uuid4()), owner_id=user["id"], title=payload.title)
        s.add(row)
        return serialize(row)


@router.get("/sessions/{sid}")
def get_session(sid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        row = get_owned(s, ResearchSession, sid, user["id"])
        if not row:
            raise HTTPException(404, "Research session not found")
        messages = s.scalars(
            select(ResearchMessage)
            .where(ResearchMessage.session_id == sid, ResearchMessage.owner_id == user["id"])
            .order_by(ResearchMessage.created_at)
        ).all()
        out = []
        for m in messages:
            d = serialize(m)
            cs = s.scalars(select(Citation).where(Citation.message_id == m.id)).all()
            d["citations"] = [serialize(c) for c in cs]
            out.append(d)
        return {**serialize(row), "messages": out}


@router.patch("/sessions/{sid}")
def patch_session(sid: str, payload: SessionBody, user=Depends(current_user)):
    with session_scope() as s:
        row = get_owned(s, ResearchSession, sid, user["id"])
        if not row:
            raise HTTPException(404, "Research session not found")
        row.title = payload.title
        return serialize(row)


@router.delete("/sessions/{sid}")
def delete_session(sid: str, user=Depends(current_user)):
    with session_scope() as s:
        row = get_owned(s, ResearchSession, sid, user["id"])
        if not row:
            raise HTTPException(404, "Research session not found")
        s.delete(row)
        return {"deleted": True}


@router.post("/sessions/{sid}/messages")
def ask_in_session(sid: str, payload: Question, user=Depends(current_user)):
    with SessionLocal() as s:
        if not get_owned(s, ResearchSession, sid, user["id"]):
            raise HTTPException(404, "Research session not found")
    from app.main import Ask, ask

    return ask(Ask(question=payload.question, session_id=sid), user)


@router.post("/saved")
def save(payload: SavedBody, user=Depends(current_user)):
    if payload.item_type not in {"message", "research_item", "community_post"}:
        raise HTTPException(400, "Unsupported saved item type")
    with session_scope() as s:
        model = {
            "message": ResearchMessage,
            "research_item": ResearchSession,
            "community_post": CommunityPost,
        }[payload.item_type]
        if not get_owned(s, model, payload.item_id, user["id"]):
            raise HTTPException(404, "Saved item target not found")
        old = s.scalar(
            select(SavedItem).where(
                SavedItem.owner_id == user["id"],
                SavedItem.item_type == payload.item_type,
                SavedItem.item_id == payload.item_id,
            )
        )
        if old:
            return serialize(old)
        row = SavedItem(
            id=str(uuid.uuid4()), owner_id=user["id"], item_type=payload.item_type, item_id=payload.item_id
        )
        s.add(row)
        return serialize(row)


@router.get("/saved")
def saved(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user)):
    with SessionLocal() as s:
        stmt = select(SavedItem).where(SavedItem.owner_id == user["id"])
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(SavedItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return {
            "items": [serialize(x) for x in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


@router.delete("/saved/{rid}")
def unsave(rid: str, user=Depends(current_user)):
    with session_scope() as s:
        row = get_owned(s, SavedItem, rid, user["id"])
        if not row:
            raise HTTPException(404, "Saved item not found")
        s.delete(row)
        return {"deleted": True}
