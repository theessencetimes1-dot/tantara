# TANTARA local backend

FastAPI API for the TANTARA arbitration workspace. The default mode runs without paid cloud services: SQLite stores typed domain rows, FastEmbed creates local 384 dimensional vectors, FAISS provides persistent nearest neighbor search, SQLite FTS5 provides BM25 search, and the local OpenAI compatible model generates answers.

## Local setup

Use Python 3.12. ONNX Runtime wheels are not available for this machine's system Python 3.14.

```sh
uv venv --python 3.12 backend/.venv
uv pip install -p backend/.venv/bin/python -r backend/requirements.txt -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
```

The database, FAISS index, uploads, and corpus files are under the resolved `TANTARA_DATA_DIR` (default: `backend/data/`). Unless `DATABASE_URL` is explicitly set, SQLite lives at `$TANTARA_DATA_DIR/tantara.db`. On first boot the application runs `alembic upgrade head` and enables SQLite WAL and foreign keys. Alembic works from the repository root or `backend/`. The bootstrap advocate is `advocate@tantara.local`; the initial password is `TANTARA_ADMIN_PASSWORD` (default: `tantara-local`). This password is local-only: change it through `POST /api/v1/settings/password` before using the service outside an isolated workspace.

The demo seed also creates `researcher@tantara.local` (Mira Shah, researcher role). Both demo accounts use the configured `TANTARA_ADMIN_PASSWORD`, which defaults to `tantara-local` for local workspaces only. Change the password before exposing a workspace beyond localhost. The researcher account owns a separate client, case, indexed document, task, hearing, draft, bundle, and community post for cross-user isolation checks.

Run on loopback only:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

The API prefix is `/api/v1`. Root `/health`, `/ingest/file`, and `/query` remain for legacy clients. The OpenAPI document is served at `/openapi.json`; `openapi.json` in this directory is the committed snapshot. `/api/v1/calendar` keeps its original bare-array default response for existing clients; append `?envelope=true` to receive `{items,total,page,page_size,pages}`.

## Configuration

See `.env.example`. Local defaults:

- `AI_PROVIDER=local`, `LOCAL_LLM_BASE_URL=http://192.168.0.101:8080/v1`, `LOCAL_LLM_MODEL=MiniCPM5-2B`
- `EMBEDDING_PROVIDER=fastembed`, `FASTEMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2`, `EMBEDDING_DIMENSIONS=384`
- `VECTOR_BACKEND=faiss`, SQLite, `ENABLE_CLOUD_PROVIDERS=false`
- `MAX_UPLOAD_MB=25`, `CORS_ORIGINS=http://localhost:3010`

Anthropic, Voyage, and Supabase libraries remain optional adapters. They are disabled unless explicitly selected and configured. The local LLM's embeddings endpoint is not used.

## Storage and retrieval

`app/models.py` contains SQLAlchemy 2.x models for users, cases, clients, hearings, tasks, documents, document pages/chunks, drafts and versions, research, bundles, community, preferences, ingestion jobs, audit events, and extraction fields. Request handlers use per-operation SQLAlchemy sessions and typed repository methods. Active domain tables have real columns, foreign keys, checks, and indexes; vector values are held in FAISS and a rebuild-only float32 BLOB on each chunk. FTS5 triggers track chunk insert/update/delete.

Ingestion runs in a thread pool. Job state and page-aware extraction results are persisted. PDF, DOCX, Markdown, and UTF-8 text are supported. Scanned PDFs use pypdfium2 and RapidOCR when their runtime models load. Document deletion removes its upload, rows, FTS entries, and FAISS vectors. The hybrid RetrievalService filters by owner and requested case/jurisdiction/document type, combines FTS5 BM25 and FAISS ranks with reciprocal rank fusion, and returns citations tied to actual chunks/pages.

Reconcile and rebuild the index:

```sh
cd backend
.venv/bin/python ../scripts/rebuild_index.py
```

## Demo workspace and corpus

`--demo` creates 12 demo cases, clients, participants, hearings, tasks, notes, drafts/versions, a community post, four locally generated PDF fixtures, and a merged bundle. PDFs go through the normal extraction and indexing pipeline; one fixture is image-only and exercises OCR.

```sh
cd backend
.venv/bin/python ../scripts/seed.py --demo
.venv/bin/python ../scripts/seed.py --empty
```

`--empty` retains the advocate account and clears its workspace records and vectors.

Corpus import is optional and probes sources at runtime, checks robots.txt, stores source/reuse metadata, records failures, and continues:

```sh
cd backend
.venv/bin/python ../scripts/import_corpus.py
```

The last host run indexed the official UNCITRAL arbitration page. Wikisource's robots endpoint returned 403, LCIA robots.txt disallowed the requested page, India Code timed out, and the Supreme Court/SIAC hosts failed to connect. These outcomes are recorded in `backend/data/corpus/manifest.json`; no mirror is labeled as an official edition.

## Tests and live workflows

```sh
cd backend
.venv/bin/pytest -q
```

Live Workflow A (PDF upload → extract/index → local LLM answer → page citation) and Workflow B (client/case relationships → persistence → merged PDF and Range request) run against an already started server:

```sh
.venv/bin/python tests/e2e_flows.py
```

The current test suite has 16 passing tests covering core authentication/CRUD, upload/delete consistency, page-aware PDF/DOCX/OCR extraction, retry and upload limits, AI Read provenance, duplicate conflicts, RBAC ownership, no-evidence behavior, migration cutover/idempotency, and RRF ranking. It is not yet a complete per-endpoint status-code and filtering matrix.

## Known limitations

- Prototype JSON records are retained as `*_legacy_0002` archive tables during cutover; users are preserved, but legacy case/client/task payloads are not automatically mapped into typed rows. Review or export those archives before removing them.
- Corpus results depend on network and publisher policy. In the latest probe only UNCITRAL was indexed; the other attempted sources were blocked or unavailable as recorded above.
- Rate limits are in-memory per process and reset at restart. Multi-worker deployments need a shared limiter.
- Bundle page numbering is not yet applied as a page overlay. Generated front matter and bookmarks are real; source PDF pages preserve their original rotation and dimensions.
- Strategy suggestions are excerpt-grounded outlines, not autonomous legal analysis. Drafts retain review markers and require counsel verification.
- Tests do not yet exhaustively exercise every endpoint's 401/403/404/409/422 behavior, all sort/filter combinations, upload size boundaries, or every OCR/DOCX/corrupt/retry permutation.
