"""Owner-scoped RAG adapter using the configured local model only."""

from app.config import get_settings
from app.services.retrieval import retrieval_service

DISCLAIMER = (
    "AI-generated research assistance only. Verify against current authoritative law and original sources; "
    "professional legal review is required."
)


def answer(question, top_k=5, jurisdiction="India", document_types=None, owner_id=None):
    """Retrieve scoped evidence and generate locally; never use a remote provider fallback."""
    if not owner_id:
        return {
            "status": "owner_required",
            "answer": "An authenticated workspace is required to search documents.",
            "sources": [],
            "model": None,
            "disclaimer": DISCLAIMER,
        }
    hits, retrieval_status = retrieval_service.search_with_status(
        question,
        owner_id,
        top_k=top_k,
        jurisdiction=jurisdiction,
        document_types=document_types,
    )
    sources = [
        {
            "chunk_id": str(hit["chunk_id"]),
            "document_id": str(hit["document_id"]),
            "title": hit["document_title"],
            "document_type": hit["source_type"],
            "page_number": hit["page_number"],
            "content": hit["snippet"],
            "retrieval_score": hit["retrieval_score"],
        }
        for hit in hits
    ]
    if not hits:
        return {
            "status": "no_evidence" if retrieval_status == "ok" else retrieval_status,
            "answer": "No relevant passages were found in this workspace's indexed documents.",
            "sources": [],
            "model": None,
            "disclaimer": DISCLAIMER,
        }
    from app.main import llm_answer

    generated = llm_answer(question, hits)
    if not generated:
        return {
            "status": "model_unavailable",
            "answer": "The search could not be completed because the configured language model is unavailable.",
            "answer_kind": "model_unavailable",
            "sources": sources,
            "model": None,
            "disclaimer": DISCLAIMER,
        }
    settings = get_settings()
    return {
        "status": retrieval_status,
        "answer": generated,
        "answer_kind": "model_generated",
        "sources": sources,
        "model": {"provider": settings.ai_provider, "model": settings.local_llm_model},
        "disclaimer": DISCLAIMER,
    }
