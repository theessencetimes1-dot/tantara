import io
import re
import time
import uuid

from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Case, DocumentChunk, User
from app.security import hash_password


def _auth(client, email="advocate@tantara.local"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tantara-local"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_case(client, headers, *, title="Grounding Probe Memorandum", seat="Mumbai"):
    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"title": title, "seat": seat, "claimant": "Alpha Ltd", "respondent": "Beta Ltd"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _pdf_pages(page_texts):
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    for text in page_texts:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def _upload_pdf(client, headers, case_id=None, *, title="Probe Memorandum"):
    content = _pdf_pages(
        [
            "Probe Memorandum",
            "The tribunal seat is Chennai, fixed under clause 14 of the agreement dated 3 March 2024.",
        ]
    )
    response = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={
            "title": title,
            "document_type": "memorandum",
            "jurisdiction": "India",
            **({"case_id": case_id} if case_id else {}),
        },
        files={"file": ("probe-memorandum.pdf", content, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    document_id = response.json()["document_id"]
    for _ in range(300):
        job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers)
        assert job.status_code == 200, job.text
        if job.json()["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job.json()["status"] == "ready", job.json()
    return document_id


def _assert_marker_integrity(result):
    markers = [int(number) for number in re.findall(r"\[(\d+)\]", result["answer"])]
    assert all(1 <= number <= len(result["citations"]) for number in markers)
    if result["answer_basis"] == "cited_excerpts":
        assert result["citation_count"] >= 1
        assert markers


def _ensure_researcher():
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "researcher@tantara.local"))
        if user is None:
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    name="Mira Shah",
                    email="researcher@tantara.local",
                    password_hash=hash_password("tantara-local"),
                    role="researcher",
                )
            )
            session.commit()
        return (
            user.id
            if user
            else session.scalar(select(User.id).where(User.email == "researcher@tantara.local"))
        )


def test_answer_quotes_page_two_evidence_and_surfaces_case_conflict(client):
    headers = _auth(client)
    case = _create_case(client, headers)
    document_id = _upload_pdf(client, headers, case["id"])
    question = "What is the seat of arbitration in the probe memorandum?"
    response = client.post(
        "/api/v1/ai/ask", headers=headers, json={"question": question, "case_id": case["id"], "top_k": 30}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ok"
    assert result["answer_basis"] == "cited_excerpts"
    assert "Chennai" in result["answer"] and "Mumbai" not in result["answer"]
    assert result["citation_count"] >= 1
    citation = result["citations"][0]
    assert citation["document_id"] == document_id and citation["page_number"] == 2
    assert result["supports"][0]["chunk_id"] == citation["chunk_id"]
    assert result["supports"][0]["document_id"] == document_id
    assert result["supports"][0]["page_number"] == 2
    assert "The tribunal seat is Chennai, fixed under clause 14" in result["supports"][0]["quote"]
    with SessionLocal() as session:
        chunk = session.get(DocumentChunk, result["supports"][0]["chunk_id"])
        assert chunk.document_id == document_id
        assert result["supports"][0]["quote"] in chunk.content
    assert result["conflicts"] == [
        {
            "field": "seat",
            "case_value": "Mumbai",
            "excerpt_value": "Chennai",
            "excerpt_chunk_id": citation["chunk_id"],
            "page_number": 2,
        }
    ]
    assert result["context_fields"] == []
    assert citation["score"] == citation["retrieval_score"] == citation["retreival_score"]
    _assert_marker_integrity(result)


def test_case_record_only_answer_is_labeled_and_not_inserted_into_answer(client):
    headers = _auth(client)
    case = _create_case(client, headers, title="Metadata-only matter", seat="Singapore")
    response = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "What seat is recorded on this case?", "case_id": case["id"]},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["answer_basis"] == "case_record"
    assert result["context_fields"] == [{"field": "seat", "value": "Singapore", "source": "case record"}]
    assert "Singapore" not in result["answer"]
    assert result["citations"] == result["supports"] == []
    with SessionLocal() as session:
        stored_case = session.get(Case, case["id"])
        assert stored_case.seat == result["context_fields"][0]["value"]


def test_noise_query_returns_empty_insufficient_evidence(client):
    headers = _auth(client)
    response = client.post("/api/v1/ai/ask", headers=headers, json={"question": "zzyz quuxorp plinth"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "insufficient_evidence"
    assert result["answer_basis"] == "insufficient_evidence"
    assert result["citations"] == result["supports"] == []
    assert result["total"] == 0
    assert "No indexed excerpt" in result["answer"]


def test_dead_model_returns_no_citations_or_fabricated_support(client):
    headers = _auth(client)
    case = _create_case(client, headers)
    _upload_pdf(client, headers, case["id"])
    configured = client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "dead-local-model"},
    )
    assert configured.status_code == 200
    result = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={
            "question": "What is the seat of arbitration in the probe memorandum?",
            "case_id": case["id"],
            "top_k": 30,
        },
    ).json()
    assert result["status"] == "model_unavailable"
    assert result["model"] is None
    assert result["citations"] == result["supports"] == []
    assert result["answer_basis"] == "insufficient_evidence"
    assert "Chennai" not in result["answer"] and "Mumbai" not in result["answer"]


def test_anonymous_foreign_case_and_researcher_access_boundaries(client):
    owner = _auth(client)
    case = _create_case(client, owner, title="Another user's probe")
    _upload_pdf(client, owner, case["id"], title="Another user's private document")
    _ensure_researcher()
    researcher = _auth(client, "researcher@tantara.local")
    assert client.post("/api/v1/ai/ask", json={"question": "Any indexed seat?"}).status_code == 401
    foreign = client.post(
        "/api/v1/ai/ask",
        headers=researcher,
        json={"question": "What is the seat in this document?", "case_id": case["id"]},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"
    allowed = client.post(
        "/api/v1/ai/ask", headers=researcher, json={"question": "Any indexed seat in my workspace?"}
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "insufficient_evidence"


def test_root_health_and_legacy_multipart_ingest_contract_remain_intact(client):
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "TANTARA Local Workspace API",
        "version": "1.1.0",
    }
    headers = _auth(client)
    response = client.post(
        "/ingest/file",
        headers=headers,
        data={"title": "Legacy adapter fixture"},
        files={"file": ("legacy-grounding.txt", b"Legacy multipart title and file contract.", "text/plain")},
    )
    assert response.status_code in {200, 202}
    assert set(response.json()) >= {"document_id", "job_id", "status", "duplicate", "document"}
    document_id = response.json()["document_id"]
    for _ in range(300):
        job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "ready"


def test_query_and_session_message_share_ask_grounding_payload(client):
    headers = _auth(client)
    _upload_pdf(client, headers)
    body = {"question": "What is the seat of arbitration in the probe memorandum?", "top_k": 30}
    ask = client.post("/api/v1/ai/ask", headers=headers, json=body)
    legacy = client.post("/query", headers=headers, json=body)
    assert ask.status_code == legacy.status_code == 200
    keys = (
        "status",
        "answer",
        "citations",
        "supports",
        "answer_basis",
        "context_fields",
        "conflicts",
        "model",
    )
    assert {key: ask.json()[key] for key in keys} == {key: legacy.json()[key] for key in keys}
    session = client.post("/api/v1/ai/sessions", headers=headers, json={"title": "Grounding parity"}).json()
    message = client.post(
        f"/api/v1/ai/sessions/{session['id']}/messages",
        headers=headers,
        json={"question": body["question"]},
    )
    assert message.status_code == 200
    assert {key: ask.json()[key] for key in keys} == {key: message.json()[key] for key in keys}
    _assert_marker_integrity(message.json())
