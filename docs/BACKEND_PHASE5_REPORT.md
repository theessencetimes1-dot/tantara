# Backend Phase 5 report

## AI honesty contract

Before this change, Ask handled a failed local call internally but continued to return `status: "ok"` in the reported probe, attributed the configured `MiniCPM5-2B` model, and returned a fluent 559-character answer with citations. The probe supplied the response properties and answer length, but not the answer's verbatim text or citation IDs; those are not reconstructed here.

After a local connection refusal or timeout, Ask and session-message responses use `status: "model_unavailable"`, `model: null`, `answer_kind: "model_unavailable"`, an explicit unavailable explanation, and `citations: []`. The relevant response fields are:

```json
{
  "status": "model_unavailable",
  "meta": {"retrieval_status": "ok"},
  "answer": "Relevant documents were found, but the configured language model is unavailable.",
  "answer_kind": "model_unavailable",
  "citations": [],
  "model": null
}
```

The API retains all existing keys and adds `answer_kind`. Research session records no longer persist a model name after failed generation. The `TANTARA_LOCAL_LLM_BASE_URL` environment variable is now recognized. Drafts honor the user's saved AI URL and model rather than silently using the process default. The AI settings and AI status endpoints also probe that user-configured endpoint and return its model and reachability.

| Surface | Before | Current unreachable/no-model behavior | Test |
|---|---|---|---|
| `POST /api/v1/ai/ask` | Failure response could claim success/model and return a fluent answer | `model_unavailable`, null model, explicitly tagged answer, no citations | `test_dead_user_configured_model_returns_explicit_unavailable_result`; `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| `POST /api/v1/ai/sessions/{id}/messages` | Delegated to the same Ask response | Same honest Ask response | `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| `POST /api/v1/documents/{id}/ai-read` | Local extraction was labelled as suggested AI fields without stating model use | `status: local_extraction`, `model: null`; route runs local text extraction and makes no model call | `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| `POST /api/v1/drafts/generate` | Failure produced a review outline without machine-readable generation status and ignored a per-user base URL | `status: model_unavailable`, `generation_kind: review_template`, `model: null`, review warning; uses saved URL | `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| `GET /api/v1/cases/{id}/autofill` | Record values were returned without stating that no model was involved | `status: record_based`, `model: null` | `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| `POST /api/v1/cases/{id}/strategy/generate` | Deterministic excerpt/template output had no explicit mode | `status: template`, `generation_kind: excerpt_listing`, `model: null` (or `no_evidence`) | `test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` |
| Community assistance | No assistance/generation route exists in the 80-path OpenAPI snapshot | No route claims generation | OpenAPI path count and `docs/TEST_MATRIX.md` |

`test_dead_model_is_honest_on_all_generation_and_assistance_surfaces` directs the configured model to closed loopback port 9 and guards `socket.connect`; it asserts every observed connection is exactly to `127.0.0.1:9`, and that only Settings status, AI status, Ask, session Ask, and Draft make such calls. `test_reachable_local_http_model_keeps_success_contract` uses a real local HTTP server, not a patched model function, and confirms a reachable configured local endpoint retains `status: ok`, a model attribution, grounded citation, and both score spellings. `test_no_evidence_embedding_unavailable_and_model_unavailable_are_distinct` proves no evidence, embedding failure, and model failure remain distinguishable; no-evidence Drafts report missing evidence rather than falsely claiming that a model call failed.

AI Read and Autofill are intentionally explicit about being local extraction/record reads. Strategy is an excerpt-listing template, not generated prose. No remote fallback was added. `/api/v1/ai/status` and `GET /api/v1/settings/ai` now reflect the per-user configured URL.

## Retrieval quality and seed corpus

The older 240d84b probe contained four documents/four pages. It reported these same ordered fusion scores for both `seat Mumbai SIAC` and `tribunal shall consist of one arbitrator`:

| Rank | Before score |
|---:|---:|
| 1 | 0.03278688524590164 |
| 2 | 0.03225806451612903 |
| 3 | 0.015873015873015872 |
| 4 | 0.015625 |

That probe did not include titles, chunk IDs, or page numbers. The four score-only rows are the complete identity information available from that baseline; no names are guessed. The 8-document/40-page fixture now includes a real OCR-only scanned PDF, text-layer PDFs, a five-page document with a unique exact phrase on page 3, two near-duplicate agreements, and a unique-term document. A 0.25 cosine similarity floor removes unrelated semantic padding while retaining strong semantic matches.

The following are actual post-change service results from the seeded test database. Scores are reciprocal-rank fusion ranks, not confidence:

| Query | Ordered hits (`title`, page, score) |
|---|---|
| `"Sapphire Pavilion on the third calendar day"` | Page Three Motion, 3, 0.032787; Construction Contract, 2, 0.016129; Construction Contract, 4, 0.015873; Scanned Arbitration Agreement, 1, 0.015625; Scanned Arbitration Agreement, 2, 0.015385; Scanned Arbitration Agreement, 3, 0.015152; Scanned Arbitration Agreement, 4, 0.014925; Scanned Arbitration Agreement, 5, 0.014706; Page Three Motion, 5, 0.014493; Near Duplicate Arbitration Agreement A, 1, 0.014286 |
| `where will the tribunal sit` (no lexical match in the corpus) | Scanned Arbitration Agreement, 1, 0.031778; Scanned Arbitration Agreement, 5, 0.031778; Scanned Arbitration Agreement, 2, 0.031754; Scanned Arbitration Agreement, 4, 0.031754; Scanned Arbitration Agreement, 3, 0.031746; Near Duplicate Arbitration Agreement A, 1, 0.028992; Near Duplicate Arbitration Agreement A, 3, 0.028778; Near Duplicate Arbitration Agreement A, 2, 0.028191; Near Duplicate Arbitration Agreement A, 4, 0.028169; Near Duplicate Arbitration Agreement A, 5, 0.027778 |
| `ZXQORBITKEY` | Unique Term Evidence, 1, 0.032266; Unique Term Evidence, 3, 0.032266; Unique Term Evidence, 4, 0.031754; Unique Term Evidence, 2, 0.031514; Unique Term Evidence, 5, 0.031010 |
| `violet saxophone excavation quantum` | no hits (`items: []`) |

The quality checks are in `test_demo_seed_has_multpage_content_calendar_extractions_and_feed`. The general retrieval test also verifies page 999 returns an empty page with the full matching `total`, and injection-style input `' OR 1=1;--` returns no rows without changing query structure. `test_reviewable_extraction_page_refs_range_and_hybrid_search` asserts `score == retrieval_score == retreival_score` on search hits; Ask citation tests assert both spellings remain equal.

For comparison with the two original probe queries, current seeded results now vary by query:

- `seat Mumbai SIAC`: Scanned Arbitration Agreement pages 1/5/2/4/3 at 0.031778/0.031778/0.031754/0.031754/0.031746; Near Duplicate Arbitration Agreement B pages 1/3/5/2/4 at 0.028790/0.028624/0.028485/0.028175/0.028006.
- `tribunal shall consist of one arbitrator`: Scanned Arbitration Agreement pages 5/1/4/2/3 at 0.030579/0.030550/0.030550/0.030536/0.030536; Arbitration Agreement pages 2/4 at 0.030415/0.029387; Page Three Motion pages 1/4 at 0.027888/0.026838; Arbitration Agreement page 1 at 0.016393.

The E2E/API request used for the semantic ranking assertion is:

```http
GET /api/v1/search/documents?query=where%20will%20the%20tribunal%20sit
Authorization: Bearer <advocate token>
```

Search is `GET /api/v1/search/documents`; `/api/v1/search` returned 404 in the live smoke. The exact page-three request in the TestClient ranking test is:

```http
GET /api/v1/search/documents?query=%22Sapphire+Pavilion+on+the+third+calendar+day%22
Authorization: Bearer <advocate token>
```

The live HTTP smoke used that query with `page_size=1` and returned this actual envelope (the IDs are from the scratch seed DB):

```json
{
  "status": "ok",
  "items": [{
    "document_id": "6b29fa0b-df63-49a3-af18-567ba1a6f10c",
    "document_title": "Page Three Motion",
    "chunk_id": "e5a0e1ba-ce3f-492f-b180-5fbee1538eb6",
    "page_number": 3,
    "snippet": "Page Three Motion — Page 3\nUnique page three clause: Sapphire Pavilion shall host the special procedural conference on\nthe third calendar day.",
    "retreival_score": 0.03278688524590164,
    "source_type": "Page Three Motion",
    "jurisdiction": "India"
  }],
  "total": 1,
  "page": 1,
  "page_size": 1,
  "pages": 1
}
```

Live health returned `200 {"status":"ok","service":"TANTARA Local Workspace API","version":"1.1.0"}` and login returned 200. With the per-user base URL set to closed `127.0.0.1:9`, the live Ask body was:

```json
{
  "status": "model_unavailable",
  "meta": {"retrieval_status": "ok"},
  "answer": "Relevant documents were found, but the configured language model is unavailable.",
  "answer_kind": "model_unavailable",
  "citations": [],
  "follow_ups": [],
  "model": null,
  "disclaimer": "AI-generated research assistance only. Verify against current authoritative law and original sources; professional legal review is required.",
  "research_session_id": "7d7ae002-02fd-4713-8a76-4c63010f3d7f",
  "message_id": "b01a4e36-918d-42d6-8f92-a5da79a7b3fe"
}
```

The before probe did not provide the 559-character unreachable answer verbatim or the four citation records' identifiers; the report records its observed fields and does not invent the missing body. The live server was stopped after capture.

## Demo workspace states

Compared with the older probe's 4 documents/4 pages, 0 case events, 0 extraction fields, and 1 community post, the final seed SQL counts are: users 3, clients 7, cases 12, case participants 24, documents 8, document pages 40, document chunks 39, tasks 17, hearings 9, drafts 1, filing bundles 1, community posts 5, community replies 8, case events 60, and extraction fields 16. The 8 generated/indexed PDFs have 5 pages each (40 source pages; generated bundle: 44 pages). It contains an unassigned zero-case client, a case with only past hearings, a case with two future hearings, and a closed case. All demo rows retain `is_demo`. The seed test checks SQL provenance and then checks client/case API values, including `case_count: 0`, null `next_hearing_at`, and the earliest future hearing.

## Test and coverage gates

Three final full-suite runs, each with a separate scratch `TANTARA_DATA_DIR` and explicit `DATABASE_URL`:

Coverage before this round was 91% per the accepted baseline; after this round it is 92% (`TOTAL 2589 207 92%`).

1. `69 passed in 220.28s`; `TOTAL 2589 207 92%`.
2. `69 passed in 152.72s`; `TOTAL 2589 207 92%`.
3. `69 passed in 151.21s`; `TOTAL 2589 207 92%`.

The pre-final diagnostic run completed with `69 passed in 207.50s`, `TOTAL 2582 206 92%`; it began before the final settings-status and API seed assertions and is not counted as one of the three final runs.

Formatting and lint gates passed: `.venv/bin/ruff format --check .` reported `58 files already formatted`; `.venv/bin/ruff check .` reported `All checks passed!`. Fresh Alembic `upgrade head` succeeded with explicit scratch `TANTARA_DATA_DIR` and `DATABASE_URL` from both `backend/` and the repository root. Live uvicorn smoke on `127.0.0.1:8010` verified health, login, page-three hybrid search, `/api/v1/search` 404, and the closed-model Ask response; the server was stopped afterward.

OpenAPI path count: **80** total (77 `/api/v1/*` plus `/health`, `/ingest/file`, and `/query`). A path-set comparison found 80 unique matrix rows, with no missing or extra paths. `docs/TEST_MATRIX.md` names the closed-port tests for the Ask, session, AI Read, Drafts, Autofill, and Strategy rows.

## Commit list

| Commit | File |
|---|---|
| `cc8ac1f` | `backend/app/config.py` |
| `3369cde` | `backend/app/main.py` |
| `899d85e` | `backend/app/routers/documents.py` |
| `755ee2c` | `backend/app/routers/drafts.py` |
| `b510065` | `backend/app/routers/settings.py` |
| `9d80ba0` | `backend/app/routers/strategy.py` |
| `2f975eb` | `backend/app/services/retrieval.py` |
| `39345bf` | `backend/tests/test_ai_degradation.py` |
| `15028cf` | `backend/tests/test_retrieval.py` |
| `d4adfee` | `backend/tests/test_workspace_round4.py` |
| `ed0f602` | `docs/BACKEND_API.md` |
| `5a4d156` | `docs/TEST_MATRIX.md` |
| `165ff02` | `scripts/seed.py` |

This report is committed as the final file-specific commit after the entries above. No push or merge was performed.
