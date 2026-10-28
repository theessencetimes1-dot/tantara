"""Hybrid document search API backed by the RetrievalService."""

from fastapi import APIRouter, Depends, Query

from app.security import current_user
from app.routers.collections import validate_collection_ids
from app.services.retrieval import retrieval_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("")
@router.get("/documents")
def search_documents(
    query: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    case_ids: str | None = None,
    document_types: str | None = None,
    collection_id: str | None = None,
    collection_ids: str | None = None,
    user=Depends(current_user),
):
    selected = [value for value in (collection_ids or "").split(",") if value]
    if collection_id:
        selected.append(collection_id)
    selected = validate_collection_ids(selected, user["id"])
    hits, status = retrieval_service.search_with_status(
        query,
        user["id"],
        page * page_size,
        document_types=document_types.split(",") if document_types else None,
        case_ids=case_ids.split(",") if case_ids else None,
        collection_ids=selected,
    )
    total = len(hits)
    return {
        "status": status,
        "items": hits[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
