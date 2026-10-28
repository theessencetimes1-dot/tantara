# Backend Phase 2 hardening report

## Deterministic migrations and isolated fixtures

The full-suite failure was caused by `TANTARA_DATA_DIR` taking precedence over
the test fixture's `DATA_DIR`. With a process-level scratch directory, fixtures
could therefore reuse an external SQLite database. The shared client fixture
now sets `TANTARA_DATA_DIR` explicitly, removes the lower-priority alias,
disposes and resets both SQLAlchemy globals, and clears
the lazily initialized FAISS store before and after each test. It drains the
document ingestion executor at fixture boundaries so a background job cannot
write into the next test's database or index. The migration helper follows the
same per-test data directory, points Alembic directly at that test database,
clears cached settings, upgrades to `head` twice, and disposes its engine.

Three consecutive runs used distinct clean temporary data directories with
`TANTARA_DATA_DIR=$(mktemp -d) .venv/bin/pytest -q --cov=app --cov-report=term-missing`.
Their test and coverage summaries were identical:

```text
Run 1: 42 passed in 106.29s (0:01:46); TOTAL 2455 357 85%
Run 2: 42 passed in 81.61s (0:01:21); TOTAL 2455 357 85%
Run 3: 42 passed in 84.13s (0:01:24); TOTAL 2455 357 85%
```

Final exact coverage line:

```text
TOTAL                                2455    357    85%
```

This meets the requested 85% total line coverage threshold. The expanded tests
exercise retrieval's lexical-only degradation, index reconciliation, vector
store operations through the API, and every router, though branches in bundle
and document edge handling remain uncovered.

## CORS

The default origin list now contains all ports 3000 through 3020 for both
`localhost` and `127.0.0.1`. `CORS_ORIGINS` and `TANTARA_CORS_ORIGINS` remain
comma-separated overrides. Both example environment files carry the same
default list.

The CORS tests cover the two requested preflights, an origin outside the allow
list, override parsing, and unauthenticated `/api/v1/health`. The live
`OPTIONS /api/v1/auth/login` smoke returned:

```text
HTTP/1.1 200 OK
access-control-allow-credentials: true
access-control-allow-origin: http://localhost:3010
```

The in-process tests also assert `http://127.0.0.1:3011` is echoed and that an
outside origin receives no `access-control-allow-origin` header.

## AI degradation and citations

`PATCH /api/v1/settings/ai` values now drive the local model URL and model used
by `/api/v1/ai/ask`. Retrieval catches query-embedding failures, continues with
owner-scoped FTS5 results, and reports `embedding_unavailable` in search while
retaining the hits. Earlier snapshots included a misspelled retrieval alias;
current API citations expose only the canonical `retrieval_score` field.

Passing tests:

- `test_dead_user_configured_model_returns_explicit_unavailable_result` sets
  the base URL to `http://127.0.0.1:9/v1`; the response is
  `model_unavailable`, contains only the explicit unavailable explanation, and
  has no citations.
- `test_embedding_failure_keeps_fts_results_and_reports_degradation` forces
  query embedding to fail and verifies the unique FTS5 evidence hit remains in
  the response with `status: embedding_unavailable`.
- `test_ai_citation_payload_keeps_both_score_spellings` verifies both score
  fields carry the same value.

## Workflows C, D, and E

These are in-process FastAPI tests using the real ingestion, SQLite, FTS5,
embedding, local model, export, and bundle code. They do not mock HTTP.

- **C — `test_workflow_c_grounded_answer_saved_citation_and_delete`:** uploads a
  two-page PDF, waits for ingestion, verifies hybrid search, asks the configured
  local model, matches the citation excerpt against the cited extracted page,
  checks both score spellings, saves the answer message, lists it, then deletes
  it.
- **D — `test_workflow_d_grounded_draft_versions_regeneration_and_exports`:**
  lists templates, generates a draft from an uploaded source, verifies a real
  chunk ID is in the source list, records and reads versions, edits and
  regenerates a section, exports DOCX and PDF, verifies MIME types and non-empty
  bytes, then opens the DOCX ZIP and checks `word/document.xml` for the section
  heading.
- **E — `test_bundle_labels_rotation_and_page_count_are_preserved`:** assembles
  only source page 2 of a mixed-size, rotated two-page PDF, checks four front
  matter pages plus the requested one-page range, section and document outline
  titles, normalized rotations, bundle/source page labels, byte-exact Range
  content, and `Content-Range`.

## Gates

```text
$ .venv/bin/ruff format --check . && .venv/bin/ruff check .
53 files already formatted
All checks passed!
```

From-zero Alembic command:

```text
$ scratch=$(mktemp -d); TANTARA_DATA_DIR="$scratch" DATABASE_URL="sqlite:///$scratch/tantara.db" .venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_local_workspace, Legacy revision marker retained so existing local workspaces can upgrade.
INFO  [alembic.runtime.migration] Running upgrade 0001_local_workspace -> 0001_baseline, Create the normalized identity/document baseline and FTS5 index.
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_typed_domain_schema, Rebuild prototype JSON tables as normalized typed domain tables.
INFO  [alembic.runtime.migration] Running upgrade 0002_typed_domain_schema -> 0003_corpus_provenance, Add verifiable public-corpus provenance to uploaded documents.
INFO  [alembic.runtime.migration] Running upgrade 0003_corpus_provenance -> 0004_reconcile_legacy, Export prototype JSON rows and remove archive tables; add shared rate buckets.
INFO  [alembic.runtime.migration] Running upgrade 0004_reconcile_legacy -> 0005_bundle_page_ranges, Allow bundle items to include an explicit inclusive source page range.
```

Live smoke on `127.0.0.1:8010` used a scratch data directory and returned:

```text
health 200 {"status":"ok","service":"TANTARA Local Workspace API","version":"1.1.0"}
login 200
dashboard/summary 200
upload 202
job ready 1 page
search/documents 200 1 ok
AI ask 200 ok Mumbai (MiniCPM5-2B reachable)
bundle generate 202 ready, 5 pages
download 200
range 206 100 bytes 0-99/6112
CORS OPTIONS /auth/login 200, allow-origin http://localhost:3010, credentials true
```

The server started for the smoke was stopped afterward.

## Remaining limitation

The requested exhaustive matrix for **every one of the 80 OpenAPI paths** is
not complete. The added parameterized matrix covers all eight generic CRUD
resource families with success, validation, researcher mutation denial,
cross-owner reads, empty out-of-range lists, and deletion behavior. Nested case,
community, AI, settings, document, draft, bundle, search, auth, metadata, and
health routes have broad workflow coverage, but not every individual operation
has its own four-way success/validation/authorization/isolation/edge matrix.
The overall coverage target is met at 85%, but coverage percentage does not
replace that remaining endpoint-by-endpoint requirement.
