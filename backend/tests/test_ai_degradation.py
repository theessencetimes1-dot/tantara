import time

from app import main
from app.services import retrieval as retrieval_module


def _uploaded_evidence(client, case_id=None):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    body = b"Unique evidence marker ZXQ-771 says the arbitration seat is Mumbai."
    upload = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"case_id": case_id} if case_id else {},
        files={"file": ("evidence.txt", body, "text/plain")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["document_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{document_id}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "ready"
    return headers, document_id


def test_dead_user_configured_model_returns_explicit_unavailable_result(client):
    headers, _document_id = _uploaded_evidence(client)
    configured = client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "dead-local-model"},
    )
    assert configured.status_code == 200
    settings_status = client.get("/api/v1/settings/ai", headers=headers).json()["runtime_status"]
    provider_status = client.get("/api/v1/ai/status", headers=headers).json()["llm"]
    assert settings_status["model"] == provider_status["model"] == "dead-local-model"
    assert settings_status["reachable"] is provider_status["reachable"] is False
    assert settings_status["checked_at"].endswith("+00:00")
    response = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "Which city appears in marker ZXQ-771?"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "model_unavailable"
    assert result["model"] is None
    assert result["answer_kind"] == "model_unavailable"
    assert result["answer"] == (
        "The search could not be completed because the configured language model is unavailable."
    )
    assert result["citations"] and result["supports"]
    assert result["total"] == result["citation_count"] == len(result["citations"])
    assert "found" not in result["answer"]


def test_dead_model_is_honest_on_all_generation_and_assistance_surfaces(client, monkeypatch):
    import socket

    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    case = client.post("/api/v1/cases", headers=auth, json={"title": "Dead model surface case"}).json()
    headers, document_id = _uploaded_evidence(client, case["id"])
    configured = client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "dead-local-model"},
    )
    assert configured.status_code == 200

    attempted = []
    original_connect = socket.socket.connect

    def allow_only_configured_local_endpoint(sock, address):
        attempted.append(address)
        assert address == ("127.0.0.1", 9), f"unexpected network destination: {address}"
        return original_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", allow_only_configured_local_endpoint)

    settings_status = client.get("/api/v1/settings/ai", headers=headers).json()["runtime_status"]
    provider_status = client.get("/api/v1/ai/status", headers=headers).json()["llm"]
    assert settings_status["model"] == provider_status["model"] == "dead-local-model"
    assert settings_status["reachable"] is provider_status["reachable"] is False

    ask = client.post(
        "/api/v1/ai/ask", headers=headers, json={"question": "Which city appears in marker ZXQ-771?"}
    ).json()
    assert ask["status"] == "model_unavailable" and ask["model"] is None
    assert ask["answer_kind"] == "model_unavailable" and ask["citations"] and ask["supports"]
    assert ask["total"] == len(ask["citations"])
    assert "evidence is available" not in ask["answer"].lower()
    assert "dead-local-model" not in ask["answer"]

    session = client.post("/api/v1/ai/sessions", headers=headers, json={"title": "Closed model"}).json()
    session_answer = client.post(
        f"/api/v1/ai/sessions/{session['id']}/messages",
        headers=headers,
        json={"question": "Which city appears in marker ZXQ-771?"},
    ).json()
    assert session_answer["status"] == "model_unavailable" and session_answer["model"] is None
    assert session_answer["answer_kind"] == "model_unavailable"
    assert "dead-local-model" not in session_answer["answer"]
    assert session_answer["citations"] and session_answer["supports"]
    assert session_answer["total"] == len(session_answer["citations"])

    read = client.post(f"/api/v1/documents/{document_id}/ai-read", headers=headers).json()
    assert read["status"] == "local_extraction" and read["model"] is None
    assert read.get("kind", read["status"]) == "local_extraction"
    assert read["fields"]["arbitration_clause"]["value"]["found"] is False

    draft = client.post(
        "/api/v1/drafts/generate",
        headers=headers,
        json={
            "case_id": case["id"],
            "document_type": "Statement of Claim",
            "source_document_ids": [document_id],
            "instructions": "Use the uploaded evidence.",
        },
    ).json()
    assert draft["status"] == "model_unavailable" and draft["model"] is None
    assert draft["generation_kind"] == "review_template"
    assert "unavailable" in " ".join(draft["warnings"])
    assert "dead-local-model" not in str(draft)

    autofill = client.get(f"/api/v1/cases/{case['id']}/autofill", headers=headers).json()
    assert autofill["status"] == "record_based" and autofill["model"] is None
    assert "dead-local-model" not in str(autofill)
    strategy = client.post(f"/api/v1/cases/{case['id']}/strategy/generate", headers=headers).json()
    assert strategy["status"] == "model_unavailable" and strategy["model"] is None
    assert strategy["generation_kind"] == "source_excerpt_review"
    assert strategy["key_issues"] == strategy["counterarguments"] == []
    assert "assembled without a model" in strategy["generation_note"]
    assert "dead-local-model" not in str(strategy)

    assert attempted and set(attempted) == {("127.0.0.1", 9)}
    assert len(attempted) == 6  # includes Strategy generation


def test_no_evidence_embedding_unavailable_and_model_unavailable_are_distinct(client, monkeypatch):
    headers, _document_id = _uploaded_evidence(client)
    client.patch(
        "/api/v1/settings/ai",
        headers=headers,
        json={"base_url": "http://127.0.0.1:9/v1", "model": "dead-local-model"},
    )
    no_evidence = client.post(
        "/api/v1/ai/ask", headers=headers, json={"question": "qzxvflibbertigibbet"}
    ).json()
    assert no_evidence["status"] == "insufficient_evidence"
    assert no_evidence["model"] is None and no_evidence["citations"] == []
    case = client.post("/api/v1/cases", headers=headers, json={"title": "No evidence draft case"}).json()
    draft = client.post(
        "/api/v1/drafts/generate",
        headers=headers,
        json={"case_id": case["id"], "document_type": "Statement of Claim"},
    ).json()
    assert draft["status"] == "no_evidence" and draft["model"] is None
    assert "no indexed case evidence" in " ".join(draft["warnings"])

    monkeypatch.setattr(main, "llm_answer", lambda question, hits, **kwargs: "A locally generated answer.")
    monkeypatch.setattr(
        retrieval_module,
        "embed_query",
        lambda _question: (_ for _ in ()).throw(RuntimeError("embedding backend disabled")),
    )
    degraded = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "Which city appears in marker ZXQ-771?"},
    ).json()
    assert degraded["status"] == "embedding_unavailable"
    assert degraded["meta"]["retrieval_status"] == "embedding_unavailable"
    assert degraded["model"]["model"] == "dead-local-model"
    assert degraded["citations"]


def test_reachable_local_http_model_keeps_success_contract(client):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class LocalModel(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", "0")))
            body = json.dumps(
                {"choices": [{"message": {"content": "The seat is Mumbai [1]."}}]}
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalModel)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers, document_id = _uploaded_evidence(client)
        host, port = server.server_address
        configured = client.patch(
            "/api/v1/settings/ai",
            headers=headers,
            json={"base_url": f"http://{host}:{port}/v1", "model": "local-fixture-model"},
        )
        assert configured.status_code == 200
        result = client.post(
            "/api/v1/ai/ask",
            headers=headers,
            json={"question": "Which city appears in marker ZXQ-771?"},
        ).json()
        assert result["status"] == "ok"
        assert result["model"] == {"provider": "local", "model": "local-fixture-model"}
        assert result["answer"] == "The seat is Mumbai [1]."
        assert result["answer_kind"] == "model_synthesis"
        assert "Mumbai" in result["answer"] and "[1]" in result["answer"]
        assert result["answer_basis"] == "cited_excerpts"
        citation = result["citations"][0]
        assert citation["citation_number"] == 1
        assert citation["document_id"] == document_id
        assert "retreival_score" not in citation
        assert citation["retrieval_score"] > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_slow_local_model_times_out_to_honest_answer_without_persisting_model_text(client, monkeypatch):
    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from app import config

    monkeypatch.setenv("TANTARA_LOCAL_LLM_TIMEOUT", "0.2")
    config.get_settings.cache_clear()

    class SlowLocalModel(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("content-length", "0")))
            time.sleep(0.8)
            body = json.dumps(
                {"choices": [{"message": {"content": "The seat is Mumbai [1]."}}]}
            ).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowLocalModel)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        headers, _document_id = _uploaded_evidence(client)
        host, port = server.server_address
        configured = client.patch(
            "/api/v1/settings/ai",
            headers=headers,
            json={"base_url": f"http://{host}:{port}/v1", "model": "slow-fixture-model"},
        )
        assert configured.status_code == 200

        started = time.monotonic()
        response = client.post(
            "/api/v1/ai/ask",
            headers=headers,
            json={"question": "Which city appears in marker ZXQ-771?"},
        )
        elapsed = time.monotonic() - started

        assert response.status_code == 200
        result = response.json()
        assert elapsed < 0.9, f"configured model deadline was not applied ({elapsed:.3f}s)"
        assert result["status"] == "model_unavailable"
        assert result["answer_kind"] == "model_unavailable"
        assert result["model"] is None
        assert result["answer"] == (
            "The search could not be completed because the configured language model is unavailable."
        )
        assert "Mumbai" not in result["answer"]
        persisted = client.get(
            f"/api/v1/ai/sessions/{result['research_session_id']}", headers=headers
        )
        assert persisted.status_code == 200
        assistant_messages = [
            message for message in persisted.json()["messages"] if message["role"] == "assistant"
        ]
        assert assistant_messages[-1]["content"] == result["answer"]
        assert "Mumbai" not in assistant_messages[-1]["content"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        config.get_settings.cache_clear()


def test_embedding_failure_keeps_fts_results_and_reports_degradation(client, monkeypatch):
    headers, _document_id = _uploaded_evidence(client)

    def unavailable(_question):
        raise RuntimeError("test embedding backend outage")

    monkeypatch.setattr(retrieval_module, "embed_query", unavailable)
    response = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "ZXQ-771 arbitration Mumbai"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "embedding_unavailable"
    assert result["total"] >= 1
    assert "ZXQ-771" in result["items"][0]["snippet"]


def test_ai_citation_payload_uses_canonical_retrieval_score(client, monkeypatch):
    headers, document_id = _uploaded_evidence(client)
    monkeypatch.setattr(main, "llm_answer", lambda question, hits, **kwargs: "The seat is Mumbai.")
    response = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "What city is named near ZXQ-771?"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model"]["model"] == "MiniCPM5-2B"
    citation = response.json()["citations"][0]
    assert citation["document_id"] == document_id
    assert response.json()["supports"][0]["quote"] in citation["excerpt"]
    assert response.json()["answer_basis"] == "cited_excerpts"
    assert "retreival_score" not in citation
    assert citation["retrieval_score"] > 0
