"""Owner-scoped knowledge collections for organizing indexed documents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import SessionLocal, session_scope
from app.models import Document, KnowledgeCollection
from app.security import current_user
from app.timezone import to_utc_iso

router = APIRouter(prefix="/api/v1/collections", tags=["collections"])


class CollectionInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)


def _serialize(collection: KnowledgeCollection, document_count: int):
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "document_count": document_count,
        "created_at": to_utc_iso(collection.created_at),
        "updated_at": to_utc_iso(collection.updated_at),
    }


@router.get("")
def list_collections(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    user=Depends(current_user),
):
    with SessionLocal() as session:
        statement = (
            select(KnowledgeCollection, func.count(Document.id))
            .outerjoin(
                Document,
                (Document.collection_id == KnowledgeCollection.id)
                & (Document.owner_id == KnowledgeCollection.owner_id),
            )
            .where(KnowledgeCollection.owner_id == user["id"])
            .group_by(KnowledgeCollection.id)
            .order_by(KnowledgeCollection.name)
        )
        total = session.scalar(
            select(func.count()).select_from(
                select(KnowledgeCollection.id).where(KnowledgeCollection.owner_id == user["id"]).subquery()
            )
        ) or 0
        rows = session.execute(statement.offset((page - 1) * page_size).limit(page_size)).all()
        return {
            "items": [_serialize(row, count) for row, count in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


def validate_collection_ids(ids: list[str] | None, owner_id: str) -> list[str] | None:
    requested = list(dict.fromkeys(ids or []))
    if not requested:
        return None
    with SessionLocal() as session:
        owned = set(
            session.scalars(
                select(KnowledgeCollection.id).where(
                    KnowledgeCollection.owner_id == owner_id,
                    KnowledgeCollection.id.in_(requested),
                )
            ).all()
        )
    if owned != set(requested):
        raise HTTPException(404, "Knowledge collection not found")
    return requested


@router.post("", status_code=201)
def create_collection(payload: CollectionInput, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Collection name is required")
    with SessionLocal() as session:
        existing = session.scalar(
            select(KnowledgeCollection).where(
                KnowledgeCollection.owner_id == user["id"], KnowledgeCollection.name == name
            )
        )
        if existing:
            raise HTTPException(409, "A collection with this name already exists")
    collection = KnowledgeCollection(
        id=str(uuid.uuid4()), owner_id=user["id"], name=name, description=payload.description.strip()
    )
    with session_scope() as session:
        session.add(collection)
    return _serialize(collection, 0)


@router.patch("/{collection_id}")
def update_collection(collection_id: str, payload: CollectionInput, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Collection name is required")
    with session_scope() as session:
        collection = session.scalar(
            select(KnowledgeCollection).where(
                KnowledgeCollection.id == collection_id, KnowledgeCollection.owner_id == user["id"]
            )
        )
        if not collection:
            raise HTTPException(404, "Collection not found")
        duplicate = session.scalar(
            select(KnowledgeCollection.id).where(
                KnowledgeCollection.owner_id == user["id"],
                KnowledgeCollection.name == name,
                KnowledgeCollection.id != collection_id,
            )
        )
        if duplicate:
            raise HTTPException(409, "A collection with this name already exists")
        collection.name = name
        collection.description = payload.description.strip()
        count = session.scalar(
            select(func.count(Document.id)).where(
                Document.owner_id == user["id"], Document.collection_id == collection_id
            )
        ) or 0
        return _serialize(collection, count)


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as session:
        collection = session.scalar(
            select(KnowledgeCollection).where(
                KnowledgeCollection.id == collection_id, KnowledgeCollection.owner_id == user["id"]
            )
        )
        if not collection:
            raise HTTPException(404, "Collection not found")
        session.query(Document).filter(
            Document.owner_id == user["id"], Document.collection_id == collection_id
        ).update({Document.collection_id: None})
        session.delete(collection)
