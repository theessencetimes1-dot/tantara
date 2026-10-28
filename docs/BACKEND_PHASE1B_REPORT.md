# TANTARA Backend Phase 1B Report

Date: 2026-10-27  
Branch: `luna/backend-core`  
Starting revision: `f9411a8`  
Latest revision before this report: `f5f8feb`

## Result

The backend has been moved from generic JSON payload tables into typed SQLAlchemy 2.0 models and a repository layer, with request-scoped database sessions. The API is split into domain routers and keeps the legacy `/health`, `/ingest/file`, and `/query` adapters. Alembic now upgrades fresh databases and the prior prototype layout. The prototype tables that could not be safely mapped are preserved under `*_legacy_0002` names; user records are retained.

Persistent embeddings are stored in the FAISS index and rebuildable binary embedding columns. Retrieval uses scoped SQLite FTS5 BM25 plus FAISS, combined by reciprocal-rank fusion. AI responses cite actual chunk/document IDs, excerpts, scores, and page numbers. Empty retrieval returns `no_evidence` with no citations.

Uploads run through background ingestion jobs, with PDF page extraction, DOCX/Markdown/text support, OCR for scanned PDF pages, duplicate detection, retry, and delete cleanup across files, database rows, FTS, and FAISS. Draft exports and filing bundles produce real DOCX/PDF files; bundle downloads support byte ranges. Authenticated records are owner-scoped, role checks cover write operations, and mutations are audited.

## Endpoints delivered

- Health and legacy compatibility: `GET /health`, `POST /ingest/file`, `POST /query`.
- Auth and metadata: `POST /auth/login`, `GET /auth/me`, and the institution, case-status, dispute-category, document-type, and jurisdiction metadata endpoints.
- Workspace: CRUD clients, cases, hearings, tasks; case participants and events; case overview; calendar; dashboard summary/activity/upcoming.
- Documents: upload/list/read/update/delete; job status and retry; file download with Range; pages and text; AI Read and extraction review; scoped document search.
- AI: ask/status, persisted sessions/messages, saved items, and embedding/database/security/profile/workspace/appearance/AI settings.
- Drafting: templates, CRUD, grounded generation, versions, section regeneration, DOCX/PDF exports.
- Bundles: CRUD, ordered items and sections, preview, generate, merged PDF download with Range.
- Case tools: autofill preview/apply with provenance and verified-value protection; editable strategy generation/save.
- Community: posts, replies, tags/kinds/saved filters, bookmarks.

The committed `backend/openapi.json` contains 80 paths and 37 component schemas. See `docs/BACKEND_API.md` for route conventions and `backend/README.md` for local setup and operations.

## Verification

`backend/.venv/bin/pytest -q` completed with **16 passed in 24.27s**, exit code 0. The suite covers auth/CRUD, owner isolation and role denial, upload/delete index consistency, PDF/DOCX/OCR extraction, retry and upload bounds, duplicate conflicts, migration from fresh and prototype databases, empty-evidence behavior, and retrieval fusion. It does not yet provide a complete success/error/filter/sort matrix for every endpoint.

The live service was run on `127.0.0.1:8010` with the local FastEmbed model and configured local LLM. `backend/tests/e2e_flows.py` completed both workflows against that service:

- Workflow A uploaded a generated PDF, waited for extraction/indexing, asked the local LLM, and returned the answer “Mumbai” with a real citation to document `80364506-6124-4738-a325-f335f8486597`, chunk `52a56ce1-f58a-4bfc-a517-588d45a1be31`, page 1, retrieval score `0.03278688524590164`.
- Workflow B persisted a client/case/participant/hearing/task, generated a merged filing PDF, and verified Range. Bundle `0054f1a9-f431-48f9-b7f5-e0773591a24c` downloaded as a 5,956-byte, 5-page PDF; `Range: bytes=0-99` returned HTTP 206 with 100 bytes.

Final sanitized live curl/HTTPX smoke evidence:

```text
GET /health                     200 {"status":"ok","service":"TANTARA Local Workspace API","version":"1.1.0"}
POST /auth/login                200 token_type=bearer; local user Workspace Advocate, role=advocate
GET /dashboard/summary          200 active_cases=20, hearings_this_week=11, documents_processed=10
GET /documents?page=1&page_size=3 200; latest real upload is ready, page_count=1
POST /ai/ask                    200 status=ok, answer="Mumbai"; citations include the uploaded document on page 1 with nonzero retrieval scores
GET /bundles/0054f1a9-f431-48f9-b7f5-e0773591a24c/download 200 application/pdf, 5956 bytes, 5 pages
GET bundle download with Range  206, 100 bytes
```

The local login password and access token were not written to this report or command output. The API remains running on the required loopback address.

## Changed files

All changes are confined to the permitted backend, docs, and scripts paths:

```text
backend/README.md
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/0001_baseline.py
backend/alembic/versions/0001_local_workspace.py
backend/alembic/versions/0002_typed_domain_schema.py
backend/alembic/versions/0003_corpus_provenance.py
backend/app/db.py
backend/app/main.py
backend/app/models.py
backend/app/repositories/domain.py
backend/app/routers/ai.py
backend/app/routers/auth.py
backend/app/routers/bundles.py
backend/app/routers/cases.py
backend/app/routers/community.py
backend/app/routers/dashboard.py
backend/app/routers/documents.py
backend/app/routers/domain.py
backend/app/routers/drafts.py
backend/app/routers/meta.py
backend/app/routers/search.py
backend/app/routers/settings.py
backend/app/routers/strategy.py
backend/app/schemas.py
backend/app/security.py
backend/app/services/audit.py
backend/app/services/index_maintenance.py
backend/app/services/retrieval.py
backend/app/services/vector_store.py
backend/openapi.json
backend/tests/conftest.py
backend/tests/e2e_flows.py
backend/tests/test_api_security.py
backend/tests/test_documents_api.py
backend/tests/test_ingestion_integration.py
backend/tests/test_migrations.py
backend/tests/test_retrieval.py
docs/BACKEND_API.md
scripts/import_corpus.py
scripts/rebuild_index.py
scripts/seed.py
docs/BACKEND_PHASE1B_REPORT.md
```

## Commits

This report is the 104th one-file commit on this branch since `f9411a8`; no push or merge was performed. The final documentation commits before this report are:

- `a419231` — update backend local setup and test coverage
- `f5f8feb` — document backend API routes and conventions

All implementation work is committed in the same range; `git log --oneline f9411a8..HEAD` contains the complete per-file history.

## Seed and corpus

`scripts/seed.py --demo` creates a typed sample workspace, four locally generated PDFs including a scanned-style PDF, and indexes their actual extracted chunks. `--empty` has been run against an isolated database and leaves an empty workspace with no vectors. `scripts/import_corpus.py` probes publisher access/robots policy, records source and license provenance, and continues after errors. In the last host run, an official UNCITRAL page was imported. Wikisource was blocked by robots, LCIA robots disallowed the requested page, India Code timed out, Supreme Court and SIAC hosts failed to connect, and the Archive.org root did not provide a usable text source. These results are recorded in the local corpus manifest; no mirror is represented as an official edition.

## Remaining limitations

- Prototype case/client/task JSON payloads are preserved in archive tables but are not automatically transformed into typed records. Review/export those archives before retiring them.
- The endpoint test suite is meaningful but not exhaustive: every route does not yet have a full 200/400/401/403/404/409 and filter/sort/pagination matrix.
- Rate limiting is in-memory per process and resets on restart; multi-worker deployment needs a shared limiter.
- Bundle page ranges, ordering, generated front matter, bookmarks, and streaming are implemented; optional page-number overlays are not.
- Strategy output is a reviewable source-backed outline with separate hypotheses, not a substitute for legal analysis. Drafts include review markers when case facts are missing.
- Anthropic, Voyage, and Supabase remain optional configuration-gated adapters. Local mode uses FastEmbed and the configured local LLM; this host’s local LLM embeddings endpoint is not used.
