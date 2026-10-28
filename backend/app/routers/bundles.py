"""PDF bundle preview, assembly, bookmarks, and download."""

import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, session_scope
from app.models import BundleItem, BundleSection, Case, Document, FilingBundle, Hearing
from app.repositories.domain import get_owned
from app.security import current_user
from app.storage_paths import stored_path
from app.services.audit import record

router = APIRouter(prefix="/api/v1/bundles", tags=["bundles"])


class Items(BaseModel):
    items: list[dict] = Field(default_factory=list)


class Sections(BaseModel):
    sections: list[dict] = Field(default_factory=list)


def _items(s, bundle, user):
    rows = s.scalars(
        select(BundleItem)
        .where(BundleItem.bundle_id == bundle.id, BundleItem.owner_id == user["id"])
        .order_by(BundleItem.order)
    ).all()
    section_rows = s.scalars(
        select(BundleSection)
        .where(BundleSection.bundle_id == bundle.id, BundleSection.owner_id == user["id"])
        .order_by(BundleSection.order)
    ).all()
    section_order = {item.title: index for index, item in enumerate(section_rows)}
    if section_order:
        rows.sort(key=lambda item: (section_order.get(item.section, len(section_order)), item.order))
    out = []
    for x in rows:
        d = s.scalar(select(Document).where(Document.id == x.document_id, Document.owner_id == user["id"]))
        if not d:
            continue
        try:
            from pypdf import PdfReader

            upload_path = stored_path("uploads", d.stored_path)
            pages = len(PdfReader(upload_path).pages)
        except Exception:
            pages = 0
        page_start = x.page_start or 1
        page_end = x.page_end or pages
        if pages and (page_start < 1 or page_end < page_start or page_end > pages):
            raise HTTPException(400, "Bundle item page range is outside the source document")
        out.append(
            {
                "document_id": d.id,
                "title": d.title,
                "section": x.section,
                "order": x.order,
                "pages": max(0, page_end - page_start + 1),
                "page_start": page_start,
                "page_end": page_end,
            }
        )
    return out


@router.put("/{rid}/items")
def set_items(rid: str, payload: Items, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        if not b:
            raise HTTPException(404, "Bundle not found")
        incoming = []
        for i, x in enumerate(payload.items):
            d = s.scalar(
                select(Document).where(
                    Document.id == x.get("document_id"),
                    Document.owner_id == user["id"],
                    Document.case_id == b.case_id,
                )
            )
            if not d:
                raise HTTPException(404, "Document not found in this case")
            page_start, page_end = x.get("page_start"), x.get("page_end")
            if page_start is not None and (type(page_start) is not int or page_start < 1):
                raise HTTPException(400, "page_start must be a positive integer")
            if page_end is not None and (type(page_end) is not int or page_end < 1):
                raise HTTPException(400, "page_end must be a positive integer")
            if d.page_count and (page_start or 1) > (page_end or d.page_count):
                raise HTTPException(400, "Bundle item page range is outside the source document")
            if d.page_count and (page_end or d.page_count) > d.page_count:
                raise HTTPException(400, "Bundle item page range is outside the source document")
            incoming.append((d, x, i, page_start, page_end))
        s.query(BundleItem).filter_by(bundle_id=rid, owner_id=user["id"]).delete(synchronize_session=False)
        for d, x, i, page_start, page_end in incoming:
            s.add(
                BundleItem(
                    id=str(uuid.uuid4()),
                    owner_id=user["id"],
                    bundle_id=rid,
                    document_id=d.id,
                    section=x.get("section", "Documents"),
                    order=x.get("order", i),
                    page_start=page_start,
                    page_end=page_end,
                )
            )
        b.status = "draft"
        record(s, user["id"], "update", "bundle_items", rid)
        return {
            "items": [
                {
                    "document_id": d.id,
                    "order": x.get("order", i),
                    "section": x.get("section", "Documents"),
                    "page_start": page_start,
                    "page_end": page_end,
                }
                for d, x, i, page_start, page_end in incoming
            ]
        }


@router.put("/{rid}/sections")
def set_sections(rid: str, payload: Sections, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    with session_scope() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        if not b:
            raise HTTPException(404, "Bundle not found")
        s.query(BundleSection).filter_by(bundle_id=rid, owner_id=user["id"]).delete(synchronize_session=False)
        for i, item in enumerate(payload.sections):
            title = item.get("title")
            if not isinstance(title, str) or not title.strip():
                raise HTTPException(400, "Each bundle section requires a title")
            s.add(
                BundleSection(
                    id=str(uuid.uuid4()),
                    owner_id=user["id"],
                    bundle_id=rid,
                    title=title.strip(),
                    order=item.get("order", i),
                )
            )
        b.status = "draft"
        record(s, user["id"], "update", "bundle_sections", rid)
        return {
            "sections": [
                {"title": x.get("title"), "order": x.get("order", i)} for i, x in enumerate(payload.sections)
            ]
        }


@router.get("/{rid}/preview")
def preview(rid: str, user=Depends(current_user)):

    with SessionLocal() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        if not b:
            raise HTTPException(404, "Bundle not found")
        items = _items(s, b, user)
        settings = {
            "cover_page": True,
            "index": True,
            "synopsis": True,
            "list_of_dates": True,
            **(b.settings or {}),
        }
        front = sum(bool(settings.get(k)) for k in ("cover_page", "index", "synopsis", "list_of_dates"))
        offset = front + 1
        sections = {}
        warnings = []
        for x in items:
            if x["pages"] == 0:
                warnings.append(f"Could not read PDF: {x['title']}")
                continue
            section = x["section"]
            entry = {
                "document_id": x["document_id"],
                "title": x["title"],
                "start_page": offset,
                "end_page": offset + x["pages"] - 1,
                "pages": x["pages"],
                "page_start": x["page_start"],
                "page_end": x["page_end"],
            }
            sections.setdefault(section, []).append(entry)
            offset += x["pages"]
        stored = s.scalars(
            select(BundleSection)
            .where(BundleSection.bundle_id == rid, BundleSection.owner_id == user["id"])
            .order_by(BundleSection.order)
        ).all()
        section_order = {x.title: i for i, x in enumerate(stored)}
        ordered = sorted(sections.items(), key=lambda x: section_order.get(x[0], len(section_order)))
        return {
            "sections": [{"title": k, "items": v} for k, v in ordered],
            "total_pages": offset - 1,
            "warnings": warnings,
        }


@router.post("/{rid}/generate", status_code=202)
def generate(rid: str, user=Depends(current_user)):
    if user.get("role") == "researcher":
        raise HTTPException(403, "This role is read-only")
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    with SessionLocal() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        if not b:
            raise HTTPException(404, "Bundle not found")
        items = _items(s, b, user)
        settings = {
            "cover_page": True,
            "index": True,
            "synopsis": True,
            "list_of_dates": True,
            **(b.settings or {}),
        }
        case = s.get(Case, b.case_id) if b.case_id else None
        case_title = case.title if case else "Arbitration Filing"
        case_parties = (
            f"{case.claimant or '[REVIEW: claimant not recorded]'} v. {case.respondent or '[REVIEW: respondent not recorded]'}"
            if case
            else "[REVIEW: case parties not recorded]"
        )
        date_entries = [
            (label, getattr(case, field))
            for field, label in (
                ("filed_at", "Filing date"),
                ("notice_date", "Notice date"),
                ("limitation_date", "Limitation date"),
            )
            if case and getattr(case, field)
        ]
        if case:
            next_hearing = s.scalar(
                select(Hearing.at)
                .where(
                    Hearing.owner_id == user["id"],
                    Hearing.case_id == case.id,
                    Hearing.at >= datetime.now(UTC).replace(tzinfo=None),
                )
                .order_by(Hearing.at)
                .limit(1)
            )
            if next_hearing:
                date_entries.append(("Next hearing", next_hearing))
        docs = []
        for x in items:
            d = s.get(Document, x["document_id"])
            try:
                upload_path = stored_path("uploads", d.stored_path)
                reader = PdfReader(upload_path)
            except Exception:
                continue
            source_start = x["page_start"]
            source_end = x["page_end"]
            if source_start < 1 or source_end < source_start or source_end > len(reader.pages):
                raise HTTPException(400, "Bundle item page range is outside the source document")
            docs.append((x, reader, source_start, source_end))
    front = []
    for key, title in (
        ("cover_page", "Cover Page"),
        ("index", "Index"),
        ("synopsis", "Synopsis"),
        ("list_of_dates", "List of Dates"),
    ):
        if settings.get(key):
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=letter)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(54, 740, title)
            c.setFont("Helvetica", 11)
            c.drawString(54, 710, case_title)
            y = 675
            if title == "Cover Page":
                c.drawString(54, 680, case_parties)
                c.drawString(54, 660, "Verify all case details and filing requirements before submission.")
            elif title == "Index":
                page_number = (
                    sum(bool(settings.get(k)) for k in ("cover_page", "index", "synopsis", "list_of_dates"))
                    + 1
                )
                for x, _reader, source_start, source_end in docs:
                    selected_pages = source_end - source_start + 1
                    end_page = page_number + selected_pages - 1
                    c.drawString(
                        54,
                        y,
                        f"{x['section']} — {x['title']} (source pp. {source_start}–{source_end}; bundle pp. {page_number}–{end_page})",
                    )
                    y -= 18
                    page_number = end_page + 1
                    if y < 60:
                        c.showPage()
                        y = 740
                        c.setFont("Helvetica", 11)
            elif title == "Synopsis":
                c.drawString(54, y, case_parties)
                y -= 22
                for x, _, _, _ in docs:
                    c.drawString(54, y, f"Included source: {x['title'][:82]}")
                    y -= 18
                c.drawString(
                    54,
                    y,
                    "Review the underlying documents for full context and verify all statements before filing.",
                )
            elif title == "List of Dates":
                if date_entries:
                    for label, value in date_entries:
                        c.drawString(54, y, f"{label}: {value:%d %b %Y}")
                        y -= 20
                else:
                    c.drawString(54, y, "No case dates are recorded. Add verified dates before filing.")
                c.drawString(54, y - 16, "Verify each date against the source record.")
            c.save()
            buf.seek(0)
            front.append((title, PdfReader(buf)))
    writer = PdfWriter()
    bookmarks = []
    source_pages = 0
    for title, reader in front:
        page_start = len(writer.pages)
        writer.append(reader)
        bookmarks.append((title, page_start))
        for page in writer.pages[page_start:]:
            if page.rotation:
                page.transfer_rotation_to_content()
        for offset in range(len(writer.pages) - page_start):
            page_index = page_start + offset
            writer.set_page_label(page_index, page_index, style="/D", prefix="Bundle ", start=page_index + 1)
    section_bookmarks = {}
    for item, reader, source_start, source_end in docs:
        title = item["section"]
        if title not in section_bookmarks:
            section_bookmarks[title] = len(writer.pages)
        page_start = len(writer.pages)
        bookmarks.append((item["title"], page_start))
        writer.append(reader, pages=(source_start - 1, source_end))
        for offset, page in enumerate(writer.pages[page_start:]):
            if page.rotation:
                page.transfer_rotation_to_content()
            writer.set_page_label(
                page_start + offset,
                page_start + offset,
                style="/D",
                prefix=f"Bundle {page_start + offset + 1} · {item['title']} source p. ",
                start=source_start + offset,
            )
        source_pages += source_end - source_start + 1
    # Section bookmarks lead each section and document bookmarks identify originals.
    for title, page in section_bookmarks.items():
        writer.add_outline_item(title, page)
    for title, page in bookmarks:
        writer.add_outline_item(title, page)
    expected_pages = sum(len(reader.pages) for _, reader in front) + source_pages
    if len(writer.pages) != expected_pages:
        raise HTTPException(500, "Generated bundle page count did not match source pages")
    output = get_settings().data_dir / "bundles" / f"{rid}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as f:
        writer.write(f)
    with session_scope() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        b.output_path = f"bundles/{output.name}"
        b.status = "ready"
        record(s, user["id"], "generate", "bundle", rid)
    return {
        "job_id": str(uuid.uuid4()),
        "status": "ready",
        "pages": len(writer.pages),
        "download_url": f"/api/v1/bundles/{rid}/download",
    }


@router.get("/{rid}/download")
def download(rid: str, user=Depends(current_user)):
    with SessionLocal() as s:
        b = get_owned(s, FilingBundle, rid, user["id"])
        path = b.output_path if b else None
    if not b:
        raise HTTPException(404, "Bundle not found")
    try:
        safe_path = stored_path("bundles", path) if path else None
    except ValueError:
        safe_path = None
    if not safe_path or not safe_path.is_file():
        raise HTTPException(404, "Bundle has not been generated")
    return FileResponse(safe_path, filename=f"{rid}.pdf", media_type="application/pdf")
