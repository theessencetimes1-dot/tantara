import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from app.db import SessionLocal
from app.models import User
from app.security import hash_password


def _login(client, email="advocate@tantara.local"):
    result = client.post("/api/v1/auth/login", json={"email": email, "password": "tantara-local"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _case_with_evidence(client):
    headers = _login(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Strategy evidence matter"}).json()
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"case_id": case["id"], "document_type": "Agreement"},
        files={
            "file": ("agreement.txt", b"The agreement sets the arbitration seat in Mumbai.", "text/plain")
        },
    )
    assert uploaded.status_code == 202
    did = uploaded.json()["document_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{did}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.05)
    assert job["status"] == "ready"
    return headers, case["id"], did


def _model_server():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            request = json.loads(body)
            prompt = request["messages"][-1]["content"]
            chunk_ids = re.findall(r"\[([^\]]+) p\.\d+\]", prompt)
            citation = chunk_ids[0]
            content = {
                "case_theory": {
                    "text": "The agreement identifies Mumbai as the arbitration seat.",
                    "citations": [citation],
                },
                "key_issues": [
                    {"text": "Confirm the agreed seat from the executed agreement.", "citations": [citation]}
                ],
                "legal_arguments": [
                    {"text": "The written clause supports Mumbai as the seat.", "citations": [citation]}
                ],
                "counterarguments": [
                    {"text": "The record may contain a later amended clause.", "citations": [citation]}
                ],
                "evidence_gaps": [
                    {"text": "No later amendment is included in retrieved evidence.", "citations": [citation]}
                ],
                "strategy_plan": [
                    {
                        "text": "Verify the executed agreement and check for amendments.",
                        "citations": [citation],
                    }
                ],
            }
            response = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_strategy_local_model_generates_cited_assertions_and_persists_mode(client):
    headers, case_id, document_id = _case_with_evidence(client)
    server, thread = _model_server()
    host, port = server.server_address
    try:
        client.patch(
            "/api/v1/settings/ai",
            headers=headers,
            json={"base_url": f"http://{host}:{port}/v1", "model": "fixture-strategy-model"},
        )
        generated = client.post(f"/api/v1/cases/{case_id}/strategy/generate", headers=headers)
        assert generated.status_code == 200
        result = generated.json()
        assert result["updated_at"].endswith("+00:00")
        assert result["generated_at"].endswith("+00:00")
        assert result["status"] == "model_generated"
        assert result["model"] == {"provider": "local", "model": "fixture-strategy-model"}
        assert result["case_theory"]
        assert result["key_issues"] and result["legal_arguments"]
        assert result["counterarguments"] and result["evidence_gaps"] and result["strategy_plan"]
        assert result["citations"] and all(
            c["document_id"] == document_id and c["page_number"] for c in result["citations"]
        )
        assert result["assertion_citations"]
        assert all(
            entry["citations"]
            and all(c["document_id"] == document_id and c["page_number"] for c in entry["citations"])
            for entry in result["assertion_citations"]
        )
        assert (
            client.get(f"/api/v1/cases/{case_id}/strategy", headers=headers).json()["status"]
            == "model_generated"
        )
        edited = client.put(
            f"/api/v1/cases/{case_id}/strategy",
            headers=headers,
            json={"case_theory": "Counsel edited theory", "key_issues": ["seat"]},
        ).json()
        assert edited["status"] == "model_generated" and edited["manually_edited"] is True
        assert edited["model"] is None
        assert edited["assertion_citations"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_strategy_unreachable_model_is_excerpt_only_and_scoped(client):
    headers, case_id, document_id = _case_with_evidence(client)
    client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "closed-port-model"},
    )
    result = client.post(f"/api/v1/cases/{case_id}/strategy/generate", headers=headers).json()
    assert result["status"] == "model_unavailable" and result["model"] is None
    assert result["key_issues"] == [] and result["counterarguments"] == []
    assert "source excerpts assembled without a model" in result["generation_note"]
    assert result["legal_arguments"] and all(
        arg["support"]
        and arg["support"][0]["document_id"] == document_id
        and arg["support"][0]["page_number"]
        for arg in result["legal_arguments"]
    )
    gap_support = next(x for x in result["assertion_citations"] if x["field"] == "evidence_gaps")
    assert gap_support["citations"] and all(
        citation["document_id"] == document_id and citation["page_number"]
        for citation in gap_support["citations"]
    )
    assert (
        client.get(f"/api/v1/cases/{case_id}/strategy", headers=headers).json()["status"]
        == "model_unavailable"
    )
    assert client.post(f"/api/v1/cases/{case_id}/strategy/generate").status_code == 401

    with SessionLocal() as session:
        outsider = User(
            id="strategy-researcher",
            name="Mira Shah",
            email="researcher@tantara.local",
            password_hash=hash_password("tantara-local"),
            role="researcher",
        )
        session.add(outsider)
        session.commit()
    outsider_headers = _login(client, "researcher@tantara.local")
    assert client.get(f"/api/v1/cases/{case_id}/strategy", headers=outsider_headers).status_code in {403, 404}
    assert client.post(
        f"/api/v1/cases/{case_id}/strategy/generate", headers=outsider_headers
    ).status_code in {403, 404}


def test_strategy_without_indexed_evidence_has_distinct_no_evidence_mode(client):
    headers = _login(client)
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Empty strategy case"}).json()
    untouched = client.get(f"/api/v1/cases/{case['id']}/strategy", headers=headers).json()
    assert untouched["status"] == "template" and untouched["model"] is None
    result = client.post(f"/api/v1/cases/{case['id']}/strategy/generate", headers=headers).json()
    assert result["status"] == "no_evidence" and result["model"] is None
    assert result["citations"] == [] and result["key_issues"] == [] and result["counterarguments"] == []
    assert "No indexed evidence" in result["evidence_gaps"][0]
    assert (
        client.get(f"/api/v1/cases/{case['id']}/strategy", headers=headers).json()["status"] == "no_evidence"
    )
