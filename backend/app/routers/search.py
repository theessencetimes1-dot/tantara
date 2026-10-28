"""Hybrid document search API backed by the RetrievalService."""

from fastapi import APIRouter, Depends, Query

from app.routers.collections import validate_collection_ids
from app.schemas import SearchResponse
from app.security import current_user
from app.services.retrieval import retrieval_service

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchResponse)
@router.get("/documents", response_model=SearchResponse)
def search_documents(
    query: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    limit: int | None = Query(None, ge=1, le=100),
    case_ids: str | None = None,
    document_types: str | None = None,
    collection_id: str | None = None,
    collection_ids: str | None = None,
    user=Depends(current_user),
):
    effective_page_size = limit if limit is not None else page_size
    selected = [value for value in (collection_ids or "").split(",") if value]
    if collection_id:
        selected.append(collection_id)
    selected = validate_collection_ids(selected, user["id"])
    hits, status = retrieval_service.search_with_status(
        query,
        user["id"],
        100,
        document_types=document_types.split(",") if document_types else None,
        case_ids=case_ids.split(",") if case_ids else None,
        collection_ids=selected,
    )
    total = len(hits)
    return {
        "status": status,
        "items": hits[(page - 1) * effective_page_size : page * effective_page_size],
        "total": total,
        "page": page,
        "page_size": effective_page_size,
        "pages": (total + effective_page_size - 1) // effective_page_size,
    }
