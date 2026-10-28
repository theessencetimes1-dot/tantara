import io
import time

from app.config import get_settings
from app.db import SessionLocal
from app.models import Document
from app.storage_paths import stored_path


def auth(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def upload(client, headers, filename, data):
    return client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": (filename, data, "application/octet-stream")},
    )


def wait_job(client, headers, did):
    for _ in range(200):
        response = client.get(f"/api/v1/documents/{did}/job", headers=headers)
        if response.status_code == 200 and response.json()["status"] in {"ready", "failed"}:
            return response.json()
        time.sleep(0.05)
    raise AssertionError("ingestion job did not reach a terminal state")


def text_pdf(text):
    from reportlab.pdfgen import canvas

    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.drawString(72, 720, text)
    c.save()
    return b.getvalue()


def scanned_pdf():
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image = Image.new("RGB", (1000, 1300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=46)
    draw.text((90, 180), "ARBITRATION AGREEMENT", fill="black", font=font)
    draw.text((90, 300), "Seat of arbitration is Mumbai India", fill="black", font=font)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    stream.seek(0)
    out = io.BytesIO()
    c = canvas.Canvas(out)
    c.drawImage(ImageReader(stream), 0, 0, width=612, height=792)
    c.save()
    return out.getvalue()


def test_text_pdf_docx_and_scanned_pdf_are_page_indexed(client):
    from docx import Document as Word

    headers = auth(client)
    word = Word()
    word.add_paragraph("DOCX arbitration agreement. Seat is Mumbai.")
    docx = io.BytesIO()
    word.save(docx)
    payloads = [
        ("sample.pdf", text_pdf("PDF arbitration agreement with a Mumbai seat.")),
        ("sample.docx", docx.getvalue()),
        ("scanned.pdf", scanned_pdf()),
    ]
    for name, body in payloads:
        created = upload(client, headers, name, body)
        assert created.status_code == 202, created.text
        did = created.json()["document_id"]
        job = wait_job(client, headers, did)
        assert job["status"] == "ready", job
        pages = client.get(f"/api/v1/documents/{did}/pages", headers=headers).json()["pages"]
        assert pages and pages[0]["page_number"] == 1
        if name == "scanned.pdf":
            assert pages[0]["ocr_confidence"] is not None and "Mumbai" in pages[0]["text"]


def test_corrupt_empty_retry_and_oversize_paths(client):
    headers = auth(client)
    corrupt = upload(client, headers, "corrupt.pdf", b"%PDF-not-a-real-pdf")
    assert corrupt.status_code == 202
    did = corrupt.json()["document_id"]
    failed = wait_job(client, headers, did)
    assert failed["status"] == "failed" and failed["error"]
    with SessionLocal() as s:
        row = s.get(Document, did)
        stored_path("uploads", row.stored_path).write_bytes(text_pdf("Repaired PDF retry has valid text."))
    retried = client.post(f"/api/v1/documents/{did}/retry", headers=headers)
    assert retried.status_code == 202
    assert wait_job(client, headers, did)["status"] == "ready"
    blank = upload(client, headers, "blank.pdf", text_pdf(""))
    assert blank.status_code == 202
    blank_id = blank.json()["document_id"]
    assert wait_job(client, headers, blank_id)["status"] == "failed"
    blank_pages = client.get(f"/api/v1/documents/{blank_id}/pages", headers=headers).json()["pages"]
    assert blank_pages and "manual review required" in blank_pages[0]["warnings"][0]["warning"]
    settings = get_settings()
    old = settings.max_upload_mb
    settings.max_upload_mb = 1
    try:
        assert (
            client.post(
                "/api/v1/documents/upload",
                headers=headers,
                files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
            ).status_code
            == 413
        )
    finally:
        settings.max_upload_mb = old
