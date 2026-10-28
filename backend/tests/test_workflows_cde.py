import io
import time
import zipfile

from reportlab.pdfgen import canvas


def _source_pdf():
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 720, "The seat of arbitration is Mumbai under clause ZXQ-WORKFLOW-500.")
    pdf.showPage()
    pdf.drawString(72, 720, "The claimant must give written notice before commencing arbitration.")
    pdf.save()
    return stream.getvalue()


def _login(client):
    result = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _case_and_document(client, headers):
    case = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"title": "Workflow case", "claimant": "Claimant Ltd", "respondent": "Respondent Ltd"},
    )
    assert case.status_code == 201
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("workflow-source.pdf", _source_pdf(), "application/pdf")},
        data={"title": "Workflow source", "case_id": case.json()["id"]},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["document_id"]
    for _ in range(150):
        job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "ready" and job["pages"] == 2
    return case.json(), document_id


def test_workflow_c_grounded_answer_saved_citation_and_delete(client):
    headers = _login(client)
    case, document_id = _case_and_document(client, headers)
    search = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "ZXQ-WORKFLOW-500 arbitration seat Mumbai"},
    )
    assert search.status_code == 200 and search.json()["total"] > 0
    answer = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={
            "question": "What city is named as the seat in clause ZXQ-WORKFLOW-500?",
            "case_id": case["id"],
        },
    )
    assert answer.status_code == 200 and answer.json()["status"] == "ok"
    citation = next(x for x in answer.json()["citations"] if x["document_id"] == document_id)
    pages = client.get(f"/api/v1/documents/{document_id}/pages", headers=headers).json()["pages"]
    page_text = " ".join(pages[citation["page_number"] - 1]["text"].split())
    assert citation["page_number"] == 1
    assert " ".join(citation["excerpt"].split()) in page_text
    assert "retreival_score" not in citation
    assert citation["retrieval_score"] > 0
    saved = client.post(
        "/api/v1/ai/saved",
        headers=headers,
        json={"item_type": "message", "item_id": answer.json()["message_id"]},
    )
    assert saved.status_code == 200
    listed = client.get("/api/v1/ai/saved", headers=headers).json()
    assert any(x["item_id"] == answer.json()["message_id"] for x in listed["items"])
    deleted = client.delete(f"/api/v1/ai/saved/{saved.json()['id']}", headers=headers)
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True


def test_workflow_d_grounded_draft_versions_regeneration_and_exports(client):
    headers = _login(client)
    case, document_id = _case_and_document(client, headers)
    evidence = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "ZXQ-WORKFLOW-500 arbitration seat Mumbai"},
    ).json()["items"]
    assert evidence
    templates = client.get("/api/v1/draft-templates", headers=headers)
    assert templates.status_code == 200 and templates.json()["items"]
    created = client.post(
        "/api/v1/drafts/generate",
        headers=headers,
        json={
            "case_id": case["id"],
            "document_type": "Statement of Claim",
            "source_document_ids": [document_id],
            "instructions": "State the supported seat of arbitration.",
        },
    )
    assert created.status_code == 200
    draft_id = created.json()["draft_id"]
    assert f"[{evidence[0]['chunk_id']}]" in created.json()["content_markdown"]
    versions = client.get(f"/api/v1/drafts/{draft_id}/versions", headers=headers).json()["items"]
    assert len(versions) == 1
    edited = client.post(
        f"/api/v1/drafts/{draft_id}/versions",
        headers=headers,
        json={
            "content_markdown": created.json()["content_markdown"] + "\n\nReviewed edit.",
            "change_note": "Reviewed",
        },
    )
    assert edited.status_code == 200 and edited.json()["version_number"] == 2
    regenerated = client.post(
        f"/api/v1/drafts/{draft_id}/regenerate-section",
        headers=headers,
        json={"section_heading": "Verified Seat", "instructions": "Cite the source excerpt."},
    )
    assert regenerated.status_code == 200
    assert "## Verified Seat" in regenerated.json()["content_markdown"]
    for export_format, media_type in (
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("pdf", "application/pdf"),
    ):
        exported = client.get(
            f"/api/v1/drafts/{draft_id}/export", headers=headers, params={"format": export_format}
        )
        assert exported.status_code == 200 and exported.content
        assert exported.headers["content-type"].startswith(media_type)
        if export_format == "docx":
            with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
                document_xml = archive.read("word/document.xml").decode()
            assert "Verified Seat" in document_xml
