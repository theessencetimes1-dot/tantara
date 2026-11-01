import time
from contextlib import suppress
from types import SimpleNamespace

from app import main
from app.services import retrieval as retrieval_module


def test_anthropic_model_selection_ignores_local_preference_and_honors_claude(client, monkeypatch):
    import sys

    headers, document_id = _uploaded_evidence(client)
    with main.SessionLocal() as session:
        document = session.get(main.Document, document_id)
        chunk = session.scalar(main.select(main.DocumentChunk).where(main.DocumentChunk.document_id == document_id))
        hit = {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_title": document.title,
            "page_number": chunk.page_number,
            "snippet": chunk.content,
            "retrieval_score": 1.0,
            "source_type": "uploaded_document",
            "jurisdiction": document.jurisdiction or "India",
            "visibility": document.visibility,
        }
    monkeypatch.setattr(main, "retrieve", lambda *_args, **_kwargs: ([hit], "ok"))
    settings = main.get_settings().model_copy(
        update={"ai_provider": "anthropic", "enable_cloud_providers": True, "claude_model": "claude-sonnet-test"}
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    requested_models = []

    class Messages:
        def create(self, **kwargs):
            requested_models.append(kwargs["model"])
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")])

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=lambda **_kwargs: SimpleNamespace(messages=Messages())),
    )

    for preference_model, expected_model in (
        ("MiniCPM5-2B", "claude-sonnet-test"),
        ("claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001"),
    ):
        saved = client.patch("/api/v1/settings/ai", headers=headers, json={"model": preference_model})
        assert saved.status_code == 200
        response = client.post(
            "/api/v1/ai/ask", headers=headers, json={"question": "Which city appears in marker ZXQ-771?"}
        )
        assert response.status_code == 200
        assert requested_models[-1] == expected_model

    assert requested_models == ["claude-sonnet-test", "claude-haiku-4-5-20251001"]
    assert main.configured_llm_model("MiniCPM5-2B") == "claude-sonnet-test"
    assert main.configured_llm_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5-20251001"


def test_anthropic_ai_status_reports_cloud_model_without_base_url(client, monkeypatch):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    settings = main.get_settings().model_copy(
        update={"ai_provider": "anthropic", "enable_cloud_providers": True, "claude_model": "claude-sonnet-test"}
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "llm_answer", lambda *_args, **_kwargs: "ok")

    llm_status = client.get("/api/v1/ai/status", headers=headers).json()["llm"]

    assert llm_status["provider"] == "anthropic"
    assert llm_status["model"] == "claude-sonnet-test"
    assert llm_status["reachable"] is True
    assert llm_status["enable_cloud_providers"] is True
    assert "base_url" not in llm_status


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
    assert draft["generation_kind"] == "unavailable"
    assert draft["content_markdown"] == ""
    assert draft["message"] and draft["citations"]
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


def test_well_cited_model_answer_with_heading_and_leadin_is_returned_as_synthesis(client, monkeypatch):
    from app import main

    headers, _document_id = _uploaded_evidence(client)
    model_text = "## Sections 9 and 17\nThe tribunal may order interim measures [1].\nIn practice, this supports urgent relief.\nThe order binds the parties [1]."
    monkeypatch.setattr(main, "llm_answer", lambda *_args, **_kwargs: model_text)
    result = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "Which city appears in marker ZXQ-771?"},
    ).json()

    assert result["answer_kind"] == "model_synthesis"
    assert result["answer"].startswith("## Sections 9 and 17\n")
    assert "[unverified] In practice, this supports urgent relief." in result["answer"]
    assert result["citations"] and result["follow_ups"] is not None


def test_model_answer_with_bold_headings_and_evidence_caveats_returns_as_prose(client, monkeypatch):
    headers, document_id = _uploaded_evidence(client)
    with main.SessionLocal() as session:
        document = session.get(main.Document, document_id)
        chunk = session.scalar(main.select(main.DocumentChunk).where(main.DocumentChunk.document_id == document_id))
        hit = {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_title": document.title,
            "page_number": chunk.page_number,
            "snippet": chunk.content,
            "retrieval_score": 1.0,
            "source_type": "uploaded_document",
            "jurisdiction": "India",
            "visibility": document.visibility,
        }
    hits = [hit, hit, hit]
    supports = [
        {"chunk_id": hit["chunk_id"], "document_id": document_id, "page_number": hit["page_number"],
         "quote": hit["snippet"], "_hit": hit}
        for hit in hits
    ]
    model_text = (
        "**Section 9 (court interim relief)**\n\n"
        "The excerpts only partly answer this. Under [1], a party may, before or during arbitral proceedings, "
        "or at any time after the arbitral award but before it is enforced, apply to a court for preservation of an asset. "
        "The excerpt does not state any further conditions, such as the legal test, grounds, or showings the applicant must make. "
        "The evidence is insufficient to say more.\n\n"
        "**Section 17 (tribunal interim measures)**\n\n"
        "Under [2], the arbitral tribunal may, during the arbitral proceedings, make an interim measure or order. "
        "The excerpt does not list the types of measures a tribunal may order, so the evidence is insufficient to identify them.\n\n"
        "[3] states that every order of the arbitral tribunal under this section is deemed to be an order of the Court "
        "for all purposes and is enforceable as if it were an order of a Court."
    )
    monkeypatch.setattr(main, "retrieve", lambda *_args, **_kwargs: (hits, "ok"))
    monkeypatch.setattr(main, "select_supports", lambda *_args, **_kwargs: supports)
    monkeypatch.setattr(main, "llm_answer", lambda *_args, **_kwargs: model_text)

    response = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "What do sections 9 and 17 provide?"},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["answer_kind"] == "model_synthesis"
    assert "**Section 9 (court interim relief)**" in result["answer"]
    assert "Under [1], a party may" in result["answer"]
    assert "The excerpt does not state any further conditions" in result["answer"]
    assert "**Section 17 (tribunal interim measures)**" in result["answer"]
    assert "Under [2], the arbitral tribunal may" in result["answer"]
    assert "states that every order" in result["answer"]
    assert "[3]" in result["answer"]
    assert "[unverified]" not in result["answer"]


def test_model_answer_with_out_of_range_marker_uses_transparent_evidence_fallback(client, monkeypatch):
    from app import main

    headers, _document_id = _uploaded_evidence(client)
    monkeypatch.setattr(main, "llm_answer", lambda *_args, **_kwargs: "The rule applies [9].")
    result = client.post(
        "/api/v1/ai/ask",
        headers=headers,
        json={"question": "Which city appears in marker ZXQ-771?"},
    ).json()

    assert result["answer_kind"] == "cited_excerpts"
    assert result["answer"].startswith("The model could not provide a validated explanation")
    assert "retrieved excerpts are shown for review" in result["answer"]
    assert "“" in result["answer"] and "[1]" in result["answer"]
    assert "[9]" not in result["answer"]


def test_model_answer_without_citation_markers_is_rejected():
    from app.main import _validated_model_synthesis

    assert _validated_model_synthesis("The rule applies.", 3) is None


def test_model_answer_uncited_content_is_explicitly_marked_unverified():
    from app.main import _validated_model_synthesis

    answer = _validated_model_synthesis(
        "Relevant provisions:\nThe tribunal may order relief [1].\n"
        "It may act promptly [1].\nThis can be urgent.",
        3,
    )

    assert answer == (
        "Relevant provisions:\nThe tribunal may order relief [1].\n"
        "It may act promptly [1].\n[unverified] This can be urgent."
    )


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
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

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
