"""Owner-scoped local arbitration community discussions and saves."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import SessionLocal, session_scope
from app.models import CommunityReply, SavedItem
from app.repositories.domain import serialize
from app.routers.domain import add_community_author, visible_community_post
from app.security import current_user
from app.services.audit import record

router = APIRouter(prefix="/api/v1/community/posts", tags=["community"])


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


@router.get("/{pid}/replies")
def replies(
    pid: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user)
):
    with SessionLocal() as s:
        if not visible_community_post(s, pid, user["id"]):
            raise HTTPException(404, "Post not found")
        stmt = select(CommunityReply).where(CommunityReply.post_id == pid)
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(CommunityReply.created_at).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = [serialize(x) for x in rows]
        for item in items:
            add_community_author(s, item)
            item.pop("owner_id", None)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


@router.post("/{pid}/replies")
def reply(pid: str, payload: ReplyBody, user=Depends(current_user)):
    with session_scope() as s:
        if not visible_community_post(s, pid, user["id"]):
            raise HTTPException(404, "Post not found")
        row = CommunityReply(id=str(uuid.uuid4()), owner_id=user["id"], post_id=pid, body=payload.body)
        s.add(row)
        record(s, user["id"], "create", "community_reply", row.id)
        result = serialize(row)
        add_community_author(s, result)
        result.pop("owner_id", None)
        return result


@router.delete("/{pid}/replies/{rid}")
def delete_reply(pid: str, rid: str, user=Depends(current_user)):
    with session_scope() as s:
        if not visible_community_post(s, pid, user["id"]):
            raise HTTPException(404, "Post not found")
        row = s.scalar(select(CommunityReply).where(CommunityReply.id == rid, CommunityReply.post_id == pid))
        if not row:
            raise HTTPException(404, "Reply not found")
        if row.owner_id != user["id"] and user.get("role") != "admin":
            raise HTTPException(403, "Only the reply author or an admin may delete it")
        s.delete(row)
        return {"deleted": True}


@router.post("/{pid}/save")
def save_post(pid: str, user=Depends(current_user)):
    with session_scope() as s:
        if not visible_community_post(s, pid, user["id"]):
            raise HTTPException(404, "Post not found")
        row = s.scalar(
            select(SavedItem).where(
                SavedItem.owner_id == user["id"],
                SavedItem.item_type == "community_post",
                SavedItem.item_id == pid,
            )
        )
        if row:
            s.delete(row)
            return {"saved": False}
        row = SavedItem(id=str(uuid.uuid4()), owner_id=user["id"], item_type="community_post", item_id=pid)
        s.add(row)
        return {"saved": True, "id": row.id}
