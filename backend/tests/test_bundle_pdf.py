import io
import time

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


def _two_page_mixed_pdf():
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    pdf.drawString(72, 720, "First page content for bundle integrity.")
    pdf.showPage()
    pdf.setPageSize((400, 700))
    pdf.drawString(72, 640, "Second page content with a different page size.")
    pdf.save()
    source = PdfReader(io.BytesIO(buffer.getvalue()))
    writer = PdfWriter()
    writer.append(source)
    writer.pages[1].rotate(90)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_bundle_labels_rotation_and_page_count_are_preserved(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Bundle PDF integrity"}).json()
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("mixed.pdf", _two_page_mixed_pdf(), "application/pdf")},
        data={"case_id": case["id"], "title": "Mixed Size Exhibit"},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["document_id"]
    for _ in range(120):
        job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "ready" and job["pages"] == 2

    bundle = client.post(
        "/api/v1/bundles",
        headers=headers,
        json={"case_id": case["id"], "name": "Integrity Bundle"},
    ).json()
    sections = client.put(
        f"/api/v1/bundles/{bundle['id']}/sections",
        headers=headers,
        json={"sections": [{"title": "Evidence", "order": 1}]},
    )
    assert sections.status_code == 200 and sections.json()["sections"][0]["title"] == "Evidence"
    assert (
        client.put(
            f"/api/v1/bundles/{bundle['id']}/items",
            headers=headers,
            json={
                "items": [{"document_id": document_id, "section": "Evidence", "page_start": 2, "page_end": 2}]
            },
        ).status_code
        == 200
    )
    preview = client.get(f"/api/v1/bundles/{bundle['id']}/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["total_pages"] == 5
    assert preview.json()["sections"][0]["title"] == "Evidence"
    generated = client.post(f"/api/v1/bundles/{bundle['id']}/generate", headers=headers)
    assert generated.status_code == 202
    response = client.get(f"/api/v1/bundles/{bundle['id']}/download", headers=headers)
    detail = client.get(f"/api/v1/bundles/{bundle['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["page_count"] == 5
    assert detail.json()["sections"] == [{"title": "Evidence", "order": 1}]
    assert detail.json()["items"][0]["page_start"] == 2
    reader = PdfReader(io.BytesIO(response.content))
    requested_source_pages = 2 - 2 + 1
    assert len(reader.pages) == 4 + requested_source_pages
    assert generated.json()["pages"] == len(reader.pages)
    assert reader.page_labels == [
        "Bundle 1",
        "Bundle 2",
        "Bundle 3",
        "Bundle 4",
        "Bundle 5 · Mixed Size Exhibit source p. 2",
    ]
    assert [page.rotation for page in reader.pages] == [0] * 5
    outline_titles = [item.title for item in reader.outline]
    assert "Evidence" in outline_titles and "Mixed Size Exhibit" in outline_titles
    assert reader.pages[-1].extract_text().find("Second page content") >= 0
    assert reader.pages[-1].extract_text().find("First page content") == -1
    ranged = client.get(
        f"/api/v1/bundles/{bundle['id']}/download", headers={**headers, "Range": "bytes=0-99"}
    )
    assert ranged.status_code == 206 and ranged.content == response.content[:100]
    assert ranged.headers["content-range"] == f"bytes 0-99/{len(response.content)}"
