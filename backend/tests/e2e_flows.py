"""Live Workflow A/B acceptance flows against http://127.0.0.1:8010."""

import io
import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from pypdf import PdfReader

BASE = "http://127.0.0.1:8010/api/v1"


def pdf_fixture(body):
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "TANTARA E2E generated evidence")
    for i, line in enumerate(body.splitlines()):
        c.drawString(72, 690 - i * 18, line[:100])
    c.save()
    buf.seek(0)
    return buf.getvalue()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run():
    password = os.environ.get("TANTARA_ADMIN_PASSWORD", "tantara-local")
    with httpx.Client(base_url=BASE, timeout=120, trust_env=False) as client:
        status = client.get("/health")
        require(status.is_success, f"API unavailable: {status.status_code} {status.text}")
        login = client.post("/auth/login", json={"email": "advocate@tantara.local", "password": password})
        require(login.is_success, f"Login failed: {login.text}")
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        ai_response = client.get("/ai/status")
        require(ai_response.is_success, ai_response.text)
        ai = ai_response.json()
        if not ai["llm"]["reachable"]:
            raise RuntimeError("SKIPPED Workflow A: configured local LLM is unreachable")
        # Workflow A: source PDF -> background extraction -> embedding/index -> grounded answer.
        matter = client.post(
            "/cases",
            json={
                "title": "E2E Evidence Matter " + uuid.uuid4().hex[:8],
                "status": "active",
                "forum": "SIAC",
                "seat": "Mumbai, India",
            },
        )
        require(matter.is_success, f"Case create failed: {matter.text}")
        case_a = matter.json()["id"]
        source = pdf_fixture(
            "The arbitration clause states that the seat of arbitration is Mumbai.\nReference phrase: TANTARA-LIVE-CITATION-7319."
        )
        upload = client.post(
            "/documents/upload",
            files={"file": ("e2e-evidence.pdf", source, "application/pdf")},
            data={
                "title": "E2E seat evidence",
                "document_type": "Arbitration Agreement",
                "jurisdiction": "India",
                "case_id": case_a,
            },
        )
        require(upload.status_code == 202, f"Upload failed: {upload.status_code} {upload.text}")
        did = upload.json()["document_id"]
        job = {}
        for _ in range(90):
            response = client.get(f"/documents/{did}/job")
            require(response.is_success, response.text)
            job = response.json()
            if job["status"] in {"ready", "failed"}:
                break
            time.sleep(0.5)
        require(job.get("status") == "ready", f"Ingestion failed: {job}")
        pages = client.get(f"/documents/{did}/pages").json()["pages"]
        require(bool(pages) and pages[0]["page_number"] == 1, "No page-aware extraction")
        answer = client.post(
            "/ai/ask",
            json={
                "question": "What city is named as the seat of arbitration?",
                "case_id": case_a,
                "top_k": 5,
            },
        )
        require(answer.is_success, f"AI ask failed: {answer.text}")
        result = answer.json()
        require(result["status"] == "ok", f"Local model did not answer: {result['status']}")
        citations = [c for c in result["citations"] if c["document_id"] == did and c["page_number"] == 1]
        require(bool(citations), f"No verified page citation for uploaded PDF: {result['citations']}")
        print("Workflow A: upload, extract, index, local LLM answer, and page citation passed.")
        print({"status": result["status"], "answer": result["answer"], "citation": citations[0]})
        # Workflow B: create workspace objects, then re-read them through the API.
        client_row = client.post(
            "/clients", json={"name": "E2E Client " + uuid.uuid4().hex[:8], "organization": "E2E Local"}
        )
        require(client_row.is_success, f"Client create failed: {client_row.text}")
        client_id = client_row.json()["id"]
        case = client.post(
            "/cases",
            json={
                "title": "E2E Case Persistence",
                "status": "active",
                "client_id": client_id,
                "forum": "ICC",
            },
        )
        require(case.is_success, f"Case create failed: {case.text}")
        case_id = case.json()["id"]
        participant = client.post(
            f"/cases/{case_id}/participants", json={"name": "E2E Counsel", "party_role": "counsel"}
        )
        require(participant.is_success, f"Participant create failed: {participant.text}")
        move = client.patch(f"/documents/{did}", json={"case_id": case_id})
        require(move.is_success, f"Document case assignment failed: {move.text}")
        at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
        hearing = client.post(
            "/hearings", json={"case_id": case_id, "title": "E2E hearing", "at": at, "mode": "online"}
        )
        require(hearing.is_success, f"Hearing create failed: {hearing.text}")
        task = client.post(
            "/tasks",
            json={
                "case_id": case_id,
                "title": "E2E review task",
                "due_at": at,
                "priority": "high",
                "status": "todo",
            },
        )
        require(task.is_success, f"Task create failed: {task.text}")
        overview = client.get(f"/cases/{case_id}/overview")
        require(overview.is_success, overview.text)
        require(
            len(overview.json()["participants"]) == 1 and overview.json()["documents_count"] == 1,
            "Reopened case did not retain relationships",
        )
        reopened = client.get(f"/cases/{case_id}")
        require(reopened.is_success and reopened.json()["client_id"] == client_id, "Case persistence failed")
        bundle = client.post(
            "/bundles",
            json={
                "case_id": case_id,
                "name": "E2E filing bundle",
                "settings": {"cover_page": True, "index": True, "synopsis": True, "list_of_dates": True},
            },
        )
        require(bundle.is_success, f"Bundle create failed: {bundle.text}")
        bid = bundle.json()["id"]
        put = client.put(
            f"/bundles/{bid}/items", json={"items": [{"document_id": did, "order": 0, "section": "Evidence"}]}
        )
        require(put.is_success, put.text)
        generated = client.post(f"/bundles/{bid}/generate")
        require(generated.is_success, f"Bundle generation failed: {generated.text}")
        download = client.get(f"/bundles/{bid}/download")
        require(download.is_success and download.content[:5] == b"%PDF-", "Bundle download is not a PDF")
        pages_count = len(PdfReader(io.BytesIO(download.content)).pages)
        require(pages_count >= 5, f"Unexpected bundle page count: {pages_count}")
        range_resp = client.get(f"/bundles/{bid}/download", headers={"Range": "bytes=0-99"})
        require(range_resp.status_code == 206 and len(range_resp.content) == 100, "Bundle byte range failed")
        print("Workflow B: client/case/participant/document/hearing/task persistence and merged PDF passed.")
        print(
            {
                "case_id": case_id,
                "bundle_id": bid,
                "bundle_pages": pages_count,
                "range_status": range_resp.status_code,
            }
        )


if __name__ == "__main__":
    run()
