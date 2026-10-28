# Backend Phase 3 report

## OCR readability and manual review

`PdfExtractor` now renders at a size-aware scale that targets a 2,000-pixel page width, caps the scale at 4x, and limits the raster to 12 megapixels. A single PDFium document and RapidOCR engine are reused across scanned pages. OCR detections are ordered and grouped using their box geometry; horizontal gaps between adjacent detections on one line become spaces. A word segmentation pass repairs fused English tokens such as `ARBITRATIONAGREEMENT` and `toarbitrationundertheArbitrationand`.

`test_scanned_agreement_uses_spacing_and_page_geometry` creates a scanned PDF using ReportLab and a PIL-rendered image. It checks the normalized clause `This agreement is referred to arbitration under the Arbitration and Conciliation Act, 1996`, the seat sentence `The seat shall be Mumbai.`, and OCR confidence above the documented **0.90** floor. `test_ocr_detection_geometry_inserts_interword_spaces` checks geometry joining, and `test_fused_ocr_tokens_are_recovered_as_legal_words` checks the reported concatenation pattern.

For the same generated fixture, the scale-2/newline-join baseline produced:

```text
This agreement is referred to arbitration under
the Arbitration and Conciliation Act, 1996.
The seat shall be Mumbai.
confidence=0.9756389369
```

The updated extractor produced:

```text
This agreement is referred to arbitration under
the Arbitration and Conciliation Act, 1996.
The seat shall be Mumbai.
confidence=0.9875393576
```

The fixture happened to retain word gaps in the baseline; the separate fused-token regression test reproduces the missing-space defect and verifies the repair. On the measured run, PDFium rasterization took **0.189 seconds per page**; cold end-to-end extraction took **9.150 seconds per page**, including OCR model initialization. These are local measurements, not performance guarantees.

If OCR cannot run, the page retains an `OCR unavailable or failed` warning and a `No usable text; manual review required` warning. A page with no usable text is persisted with its warning, and a document with no extractable text ends in `failed`; it cannot become an empty `ready` document. `test_ocr_import_failure_keeps_page_and_returns_recovery_warning` and `test_corrupt_empty_retry_and_oversize_paths` cover those cases.

## OpenAPI route matrix

[TEST_MATRIX.md](TEST_MATRIX.md) enumerates all **80 paths** in `backend/openapi.json`, with success, validation, authorization, not-found, owner-isolation, and edge-case cells. The reusable tests dynamically enumerate protected OpenAPI operations, body-bearing mutations, and paginated GET routes:

- `test_all_protected_openapi_operations_reject_anonymous_requests` checks unauthenticated requests across protected operations.
- `test_all_openapi_mutation_bodies_return_validation_envelope` checks malformed request bodies return 422 with `error.code`, `error.message`, and `error.details`.
- `test_all_openapi_paginated_get_routes_validate_page_bounds` checks invalid page bounds return that same envelope.

Owner tests use a second advocate account for case-scoped resources and assert 404 on foreign cases, documents, drafts, bundles, AI sessions, and community subresources. Generic CRUD isolation and role tests cover clients, cases, hearings, tasks, drafts, bundles, notes, and posts. List tests assert `{items,total,page,page_size,pages}` on the paginated list routes, including out-of-range empty pages. The table marks cells `N/A` where a route has no record, list, or validation surface.

## Contract stability

Search hits and AI citations assert both `retrieval_score` and legacy `retreival_score` exist and are equal. Paginated list envelopes are asserted for domain collections, documents, search, AI sessions/saved items, case events, community replies, security events, draft templates, and draft versions. Root `/health`, `/ingest/file`, and `/query` are exercised and their response shapes checked.

`GET /api/v1/documents/{id}/file` is tested for a 206 byte range with exact `Content-Range`, a full no-Range 200 response, and `HEAD` 200 with the full `Content-Length`. `tantara_admin_password` is documented in `BACKEND_API.md` as a local-only `tantara-local` default that must be changed before use outside an isolated local workspace. A tracked-worktree scan for common API-key/token/private-key formats found no matches outside `sensitive/`; `sensitive/` was not read.

## Coverage and repeated runs

The Phase 2 baseline was **85%** (`TOTAL 2455 357 85%`). Final coverage is **91%**:

```text
TOTAL                                2538    217    91%
```

The previously weak modules improved to: `index_maintenance.py` 100%, `retrieval.py` 97%, `settings.py` 98%, `strategy.py` 92%, and `security.py` 85%. The three final runs used distinct clean `TANTARA_DATA_DIR` directories and produced the same test count and coverage:

```text
Run 1: 58 passed in 182.23s (0:03:02); TOTAL 2538 217 91%
Run 2: 58 passed in 196.83s (0:03:16); TOTAL 2538 217 91%
Run 3: 58 passed in 218.54s (0:03:38); TOTAL 2538 217 91%
```

The exact test command for each run was:

```text
TANTARA_DATA_DIR=$(mktemp -d) .venv/bin/pytest -q --cov=app --cov-report=term-missing
```

Gate output:

```text
$ .venv/bin/ruff format --check . && .venv/bin/ruff check .
55 files already formatted
All checks passed!
$ TANTARA_DATA_DIR="$scratch" DATABASE_URL="sqlite:///$scratch/tantara.db" .venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_local_workspace, Legacy revision marker retained so existing local workspaces can upgrade.
INFO  [alembic.runtime.migration] Running upgrade 0001_local_workspace -> 0001_baseline, Create the normalized identity/document baseline and FTS5 index.
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_typed_domain_schema, Rebuild prototype JSON tables as normalized typed domain tables.
INFO  [alembic.runtime.migration] Running upgrade 0002_typed_domain_schema -> 0003_corpus_provenance, Add verifiable public-corpus provenance to uploaded documents.
INFO  [alembic.runtime.migration] Running upgrade 0003_corpus_provenance -> 0004_reconcile_legacy, Export prototype JSON rows and remove archive tables; add shared rate buckets.
INFO  [alembic.runtime.migration] Running upgrade 0004_reconcile_legacy -> 0005_bundle_page_ranges, Allow bundle items to include an explicit inclusive source page range.
```

## Remaining gaps

The total coverage target and path-level table are complete. `app/rag.py` remains unexercised (20 statements); its legacy implementation is not on the current router path. `security.py` remains at 85% because the standalone role-dependency and audit helpers are not directly exercised, although route authentication, role denials, token validation, and audit writes are covered. Some path-level matrix cells are `N/A` for non-resource routes by design; the matrix is path-based and does not claim a separate happy-path test for every HTTP method on a multi-method path.

## Commit record

Each changed file below is committed separately, with no push or merge:

- `backend/app/ingestion.py`
- `backend/app/routers/documents.py`
- `backend/app/routers/drafts.py`
- `backend/requirements.txt`
- `backend/tests/test_bundle_pdf.py`
- `backend/tests/test_contract_stability.py`
- `backend/tests/test_documents_api.py`
- `backend/tests/test_endpoint_matrix.py`
- `backend/tests/test_hardening_units.py`
- `backend/tests/test_ingestion_integration.py`
- `backend/tests/test_ocr_recovery.py`
- `backend/tests/test_retrieval.py`
- `backend/tests/test_settings_strategy.py`
- `docs/BACKEND_API.md`
- `docs/TEST_MATRIX.md`
- `docs/BACKEND_PHASE3_REPORT.md`

The completion message gives the resulting commit hashes. This report is itself committed as a single-file commit.
