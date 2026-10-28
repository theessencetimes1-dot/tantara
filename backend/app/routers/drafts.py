"""Grounded draft generation, version history, and real export endpoints."""

import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.models import AppPreference, Case, Document, DocumentChunk, Draft, DraftVersion, ExtractionField
from app.repositories.domain import get_owned, serialize
from app.security import current_user
from app.services.audit import record
from app.services.draft_versions import snapshot_draft

router = APIRouter(prefix="/api/v1", tags=["drafts"])
TEMPLATES = [
    "Statement of Claim",
    "Statement of Defence",
    "Rejoinder",
    "Notice Invoking Arbitration",
    "Request for Arbitration",
    "Procedural Application",
    "Interim Relief Application",
    "Written Submissions",
    "Chronology of Events",
    "List of Dates",
    "Case Summary",
    "Legal Research Memorandum",
]


class Generate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    document_type: str
    template_id: str | None = None
    instructions: str = ""
    source_document_ids: list[str] = Field(default_factory=list)
    language: str = "English"


class VersionBody(BaseModel):
    content_markdown: str | None = None
    change_note: str | None = None


class SectionBody(BaseModel):
    section_heading: str
    instructions: str = ""


@router.get("/draft-templates")
def templates(user=Depends(current_user)):
    items = [{"id": str(i + 1), "name": name, "document_type": name} for i, name in enumerate(TEMPLATES)]
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items),
        "pages": 1 if items else 0,
    }


@router.get("/drafts/{rid}/versions")
def versions(
    rid: str, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user=Depends(current_user)
):
    with SessionLocal() as s:
        if not get_owned(s, Draft, rid, user["id"]):
            raise HTTPException(404, "Draft not found")
        stmt = select(DraftVersion).where(DraftVersion.draft_id == rid, DraftVersion.owner_id == user["id"])
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = s.scalars(
            stmt.order_by(DraftVersion.version_number.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = [_serialize_version(row) for row in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }


@router.post("/drafts/{rid}/versions")
def save_version(rid: str, payload: VersionBody, user=Depends(current_user)):
    if payload.content_markdown is not None and not payload.content_markdown.strip():
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "validation_error", "message": "Draft content cannot be blank"}},
        )
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        draft = get_owned(s, Draft, rid, user["id"])
        if not draft:
            raise HTTPException(404, "Draft not found")
        row = snapshot_draft(s, draft, draft.content_markdown, payload.change_note)
        if payload.content_markdown is not None:
            draft.content_markdown = payload.content_markdown
        record(s, user["id"], "create", "draft_version", row.id)
        return _serialize_version(row)


def _serialize_version(row):
    item = serialize(row)
    if item.get("change_note") is None:
        item.pop("change_note", None)
    return item


@router.get("/drafts/{rid}/versions/{vid}")
def get_version(rid: str, vid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        if not get_owned(s, Draft, rid, user["id"]):
            raise HTTPException(404, "Draft not found")
        row = s.scalar(
            select(DraftVersion).where(
                DraftVersion.id == vid,
                DraftVersion.draft_id == rid,
                DraftVersion.owner_id == user["id"],
            )
        )
        if not row:
            raise HTTPException(404, "Draft version not found")
        return _serialize_version(row)


@router.post("/drafts/{rid}/versions/{vid}/restore")
def restore_version(rid: str, vid: str, user=Depends(current_user)):
    with session_scope() as s:
        draft = get_owned(s, Draft, rid, user["id"])
        if not draft:
            raise HTTPException(404, "Draft not found")
        source = s.scalar(
            select(DraftVersion).where(
                DraftVersion.id == vid,
                DraftVersion.draft_id == rid,
                DraftVersion.owner_id == user["id"],
            )
        )
        if not source:
            raise HTTPException(404, "Draft version not found")
        if user.get("role") == "researcher":
            raise HTTPException(403, "This role is read-only")
        if user.get("role") == "staff":
            raise HTTPException(403, "This role cannot modify this resource")
        snapshot_draft(s, draft, draft.content_markdown, f"Restored from version {source.version_number}")
        draft.content_markdown = source.content_markdown
        record(s, user["id"], "restore", "draft_version", source.id)
        return serialize(draft)


@router.post("/drafts/generate")
def generate(payload: Generate, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with SessionLocal() as s:
        case = get_owned(s, Case, payload.case_id, user["id"])
        if not case:
            raise HTTPException(404, "Case not found")
        docs = s.scalars(
            select(Document).where(
                Document.owner_id == user["id"], Document.case_id == case.id, Document.status == "ready"
            )
        ).all()
        if payload.source_document_ids:
            selected = set(payload.source_document_ids)
            docs = [d for d in docs if d.id in selected]
            if len(docs) != len(selected):
                raise HTTPException(404, "One or more source documents not found")
        title = payload.document_type
        case_info = {
            k: getattr(case, k)
            for k in ("title", "claimant", "respondent", "forum", "seat", "governing_law", "reference_number")
        }
        chunks = (
            s.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id.in_([d.id for d in docs]))
                .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
                .limit(16)
            ).all()
            if docs
            else []
        )
        doc_map = {d.id: d for d in docs}
        evidence = [
            {
                "chunk_id": x.id,
                "document_id": x.document_id,
                "document_title": doc_map[x.document_id].title,
                "page_number": x.page_number,
                "snippet": x.content[:1400],
                "source_type": doc_map[x.document_id].document_type,
                "jurisdiction": doc_map[x.document_id].jurisdiction,
            }
            for x in chunks
        ]
        reviewed = (
            s.scalars(
                select(ExtractionField).where(
                    ExtractionField.owner_id == user["id"],
                    ExtractionField.document_id.in_([d.id for d in docs]),
                    ExtractionField.provenance.in_(["verified", "extracted_reviewed"]),
                )
            ).all()
            if docs
            else []
        )
        verified_fields = {x.key: x.value for x in reviewed}
        ai_preference = s.scalar(
            select(AppPreference).where(AppPreference.owner_id == user["id"], AppPreference.key == "ai")
        )
        ai_settings = ai_preference.value if ai_preference else {}
    generated = None
    generation_status = "no_evidence"
    if evidence:
        from app.main import llm_answer

        question = (
            f"Draft a careful initial {title} for the supplied arbitration case. Use only the verified case fields and selected document excerpts below. "
            "Organize with useful headings. Cite only the supplied chunk IDs as [chunk_id]. Never invent facts, parties, authorities, dates, quotations, or relief. "
            "Mark every unsupported or missing fact with [REVIEW: ...]. This is an advocate review draft, not legal advice.\nVerified fields: "
            + str(case_info)
            + "\nReviewed extraction candidates: "
            + str(verified_fields)
            + "\nInstructions: "
            + payload.instructions
        )
        generated = llm_answer(
            question,
            evidence,
            base_url=ai_settings.get("base_url"),
            model=ai_settings.get("model"),
        )
        generation_status = "ok" if generated else "model_unavailable"
        valid = {x["chunk_id"] for x in evidence}
        if generated:
            refs = re.findall(r"\[([0-9a-fA-F-]{36})\]", generated)
            if any(ref not in valid for ref in refs):
                generated = None
                generation_status = "unverifiable_output"
    parties = f"{case_info['claimant'] or '[REVIEW: claimant not verified]'} v. {case_info['respondent'] or '[REVIEW: respondent not verified]'}"
    if generated:
        content = f"# {title}\n\n**Case:** {case_info['title']}\n**Parties:** {parties}\n\n{generated.strip()}\n\n## Counsel review\n\n[REVIEW: Verify every factual statement, legal proposition, authority, and requested relief before use.]\n"
    else:
        reason = (
            "No indexed case documents were available."
            if not evidence
            else "The local language model was unavailable or returned an unverifiable citation."
        )
        content = f"# {title}\n\n**Case:** {case_info['title']}\n**Parties:** {parties}\n\n## Background\n\n[REVIEW: {reason} Add a verified chronology and cite selected source documents.]\n\n## Submissions\n\n[REVIEW: Add arguments supported by verified authorities and evidence.]\n\n## Relief sought\n\n[REVIEW: Confirm requested relief with counsel.]\n"
    if evidence:
        source_list = "\n".join(
            f"- [{item['chunk_id']}] {item['document_title']}, page {item['page_number']}"
            for item in evidence
        )
        content += f"\n\n## Source excerpts\n\n{source_list}\n"
    did, vid = str(uuid.uuid4()), str(uuid.uuid4())
    with session_scope() as s:
        d = Draft(
            id=did,
            owner_id=user["id"],
            case_id=payload.case_id,
            title=title,
            document_type=title,
            status="draft",
            content_markdown=content,
            template_id=payload.template_id,
        )
        s.add(d)
        s.add(
            DraftVersion(
                id=vid,
                owner_id=user["id"],
                draft_id=did,
                version_number=1,
                content_markdown=content,
                change_note="Generated outline",
            )
        )
        record(s, user["id"], "generate", "draft", did)
    markers = [line.strip() for line in content.splitlines() if "[REVIEW:" in line]
    if generated:
        fallback_warnings = []
    elif not evidence:
        fallback_warnings = [
            "Generated a marked review outline because no indexed case evidence was available."
        ]
    elif generation_status == "model_unavailable":
        fallback_warnings = [
            "Generated a marked review outline because the configured local model was unavailable."
        ]
    else:
        fallback_warnings = [
            "Generated a marked review outline because model output had unverifiable citations."
        ]
    return {
        "status": generation_status,
        "generation_kind": "model_generated" if generated else "review_template",
        "model": (
            {
                "provider": get_settings().ai_provider,
                "model": ai_settings.get("model") or get_settings().local_llm_model,
            }
            if generated
            else None
        ),
        "draft_id": did,
        "version_id": vid,
        "content_markdown": content,
        "warnings": ["Draft requires legal review; verify facts, law, and citations."] + fallback_warnings,
        "review_markers": markers,
    }


@router.post("/drafts/{rid}/regenerate-section")
def regenerate(rid: str, payload: SectionBody, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    # A new marked section version preserves the preceding version unchanged.
    with SessionLocal() as s:
        d = get_owned(s, Draft, rid, user["id"])
    if not d:
        raise HTTPException(404, "Draft not found")
    content = (
        d.content_markdown
        + f"\n\n## {payload.section_heading}\n\n[REVIEW: Replace with verified material. {payload.instructions}]\n"
    )
    with session_scope() as s:
        draft = get_owned(s, Draft, rid, user["id"])
        row = snapshot_draft(
            s, draft, draft.content_markdown, f"Regenerated section: {payload.section_heading}"
        )
        draft.content_markdown = content
        record(s, user["id"], "generate", "draft_section", row.id)
        return {
            "id": row.id,
            "version_number": row.version_number,
            "content_markdown": content,
            "review_required": True,
        }


@router.get("/drafts/{rid}/export")
def export(rid: str, format: str = Query("docx", pattern="^(docx|pdf)$"), user=Depends(current_user)):
    with SessionLocal() as s:
        d = get_owned(s, Draft, rid, user["id"])
    if not d:
        raise HTTPException(404, "Draft not found")
    if not d.content_markdown.strip():
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "conflict",
                    "message": "Draft content is empty and cannot be exported",
                }
            },
        )
    output = io.BytesIO()
    if format == "docx":
        from docx import Document as WordDoc

        doc = WordDoc()
        for line in d.content_markdown.splitlines():
            doc.add_paragraph(line)
        doc.save(output)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import Paragraph
        from xml.sax.saxutils import escape
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(output, pagesize=letter)
        y = 740
        for line in d.content_markdown.splitlines():
            heading = line.lstrip().startswith("##")
            text = re.sub(r"^\s*#+\s*", "", line).strip()
            if not text:
                y -= 9
                continue
            style = ParagraphStyle(
                "DraftHeading" if heading else "DraftBody",
                fontName="Helvetica-Bold" if heading else "Helvetica",
                fontSize=14 if heading else 10,
                leading=18 if heading else 14,
                alignment=TA_LEFT,
            )
            paragraph = Paragraph(escape(text), style)
            _, height = paragraph.wrap(516, 680)
            if y - height < 48:
                c.showPage()
                y = 740
            paragraph.drawOn(c, 48, y - height)
            y -= height + (8 if heading else 5)
        c.save()
        media = "application/pdf"
    output.seek(0)
    return StreamingResponse(
        output, media_type=media, headers={"Content-Disposition": f'attachment; filename="{rid}.{format}"'}
    )
