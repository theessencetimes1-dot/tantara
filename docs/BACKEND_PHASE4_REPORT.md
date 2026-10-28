# Backend Phase 4 report

## Workspace configuration and retrieval integrity

When no `DATABASE_URL` is configured, settings resolve `data_dir` to an absolute path and derive SQLite at `<data_dir>/tantara.db`. An explicit database URL still takes precedence. The FAISS index is `<data_dir>/index`; the tests `test_data_dirs_derive_separate_database_files_with_independent_rows` and `test_database_and_faiss_store_share_resolved_data_root` verify independent rows and co-location. The obsolete `DATABASE_URL` sample was removed from `backend/env_example` because it overrode the data-directory-derived default whenever that sample file was loaded.

The repository-root `alembic.ini` points to `backend/alembic`, so `alembic upgrade head` works from either the repository root or `backend/`. Revisions `0006_derive_next_hearing` and `0007_demo_chunk_flag` remove the stale case timestamp column and preserve `is_demo` on newly ingested chunks.

If chunks exist and their ids do not match the FAISS index ids, retrieval sets `embedding_unavailable`. Search keeps its list fields and sets the top-level `status` to that value. AI ask includes `meta: {"retrieval_status": "embedding_unavailable"}` even if model availability determines the top-level status. The lexical results remain available where matched, with the warning made explicit.

## Derived API fields

`next_hearing_at` is now derived from the earliest future hearing owned by the same user and case. The persisted duplicate column is dropped by migration `0006_derive_next_hearing`. The API test `test_case_hearing_derivation_is_live_and_owner_scoped` covers past-only, two future hearings, list/detail agreement, immediate POST visibility, delete clearing, and a foreign-owned hearing row.

Client lists and details add `case_count`, counting only the current user's non-archived cases. `test_client_case_count_is_owner_scoped_and_requires_auth` proves cross-user cases do not increment it and anonymous users cannot read it. Case overview already exposes real, owner-scoped `documents_count` and `drafts_count`; they are computed directly from the documents and drafts tables by `GET /api/v1/cases/{id}/overview`, so the frontend can read them from that endpoint without paging through lists.

## Demo data reconciliation

The earlier seeded workspace was too thin: 4 documents and 4 pages, 0 case events, 0 extraction fields, and 1 community post. Running `scripts/seed.py --demo` in `/tmp/tantara-phase4-counts.8x6cwI` produced these SQL counts:

| Table | Before | After |
| --- | ---: | ---: |
| users | 3 | 3 |
| clients | 6 | 6 |
| cases | 12 | 12 |
| case_participants | 24 | 24 |
| documents | 4 | 4 |
| document_pages | 4 | 20 |
| document_chunks | — | 19 |
| tasks | 12 | 17 |
| hearings | 7 | 7 |
| drafts | 1 | 1 |
| filing_bundles | 1 | 1 |
| community_posts | 1 | 5 |
| community_replies | — | 8 |
| case_events | 0 | 60 |
| extraction_fields | 0 | 8 |

The four generated PDFs each have five pages: three text-layer documents and one image-only scanned document. The contract includes a blank page that extraction marks for manual review. All 20 document pages and 19 indexed chunks carry `is_demo=true`; the document, task, hearing, event, extraction, post, and reply rows are also demo flagged. Events and hearings use dates relative to seed time and fall across the current month and nearby weeks; tasks include overdue, due-today, and undated open examples. Extraction values include source page 1. Posts use case-derived tags and have replies.

`test_demo_seed_has_multpage_content_calendar_extractions_and_feed` verifies page counts, scan/text-layer presence, manual review, extraction fields, events in the current month, demo flags, posts/replies, and task groupings. `scripts/seed.py --empty` now removes dependent chunk rows before clearing documents, commits before rebuilding the index, deletes generated fixture files, and leaves only the advocate account. Verified SQL output: `users=1`; clients, cases, documents, pages, chunks, tasks, hearings, posts, case events, and extraction fields all `0`; index vectors `0`. `test_empty_seed_retains_only_the_local_advocate_and_no_rows` seeds a chunk first and checks the database and FAISS cleanup.

## OCR verification

The old extraction joined recognizer lines without geometry and rendered at scale 2. The previously observed text was:

```text
ARBITRATIONAGREEMENT
toarbitrationundertheArbitrationand
ConciliationAct, 1996.The seat shall beMumbai.
```

The retained reportlab-generated scanned-page fixture now renders at a size-aware scale and joins detections by their boxes. Observed output:

```text
This agreement is referred to arbitration under
the Arbitration and Conciliation Act, 1996.
The seat shall be Mumbai.
```

Observed confidence changed from `0.9887` to `0.9875`; the fixture asserts confidence above the documented `0.90` floor and checks both complete sentences. The observed render cost was approximately `4.8 s/page` for this fixture. OCR failure warnings are retained, and pages with no usable text receive the manual-review warning rather than being silently treated as extracted.

## Gates

Three clean test runs, each with a separate `TANTARA_DATA_DIR`, completed with identical pass and coverage totals:

1. `66 passed in 180.65s (0:03:00)`
2. `66 passed in 246.29s (0:04:06)`
3. `66 passed in 211.80s (0:03:31)`

Each run ended with `TOTAL 2566 218 92%`; this is one percentage point above the Phase 3 baseline (`TOTAL 2538 217 91%`) and exceeds the 90% target. The three summaries match at 66 passing tests and 92% total coverage.

Ruff, root-level fresh-database Alembic, and the scratch demo/empty seed were verified. `backend/tmp_ingest_test.txt` was removed; `test_debug_ingest_artifact_is_never_written_into_the_checkout` prevents its return. No real secret was added to the repository, and `sensitive/` was not accessed.

## Per-file commits

| Commit | File |
| --- | --- |
| `8b3b860` | `backend/README.md` |
| `ee2920c` | `backend/app/config.py` |
| `1d1b234` | `backend/app/main.py` |
| `ead5646` | `backend/app/models.py` |
| `10c34b5` | `backend/app/routers/bundles.py` |
| `88c09dd` | `backend/app/routers/cases.py` |
| `ae41e81` | `backend/app/routers/documents.py` |
| `7d62646` | `backend/app/routers/domain.py` |
| `221cec5` | `backend/app/routers/strategy.py` |
| `8444fcc` | `backend/app/services/retrieval.py` |
| `c0150e7` | `backend/env_example` |
| `936d66a` | `backend/tmp_ingest_test.txt` (deleted) |
| `33bae24` | `docs/BACKEND_API.md` |
| `9bb9945` | `scripts/seed.py` |
| `41b65c9` | `alembic.ini` |
| `0b9c8cb` | `backend/alembic/versions/0006_derive_next_hearing.py` |
| `a65ee81` | `backend/alembic/versions/0007_demo_chunk_flag.py` |
| `6dd5fc8` | `backend/tests/test_workspace_round4.py` |

`docs/BACKEND_PHASE4_REPORT.md` is committed separately after these per-file commits; its commit id is reported in the completion message.
