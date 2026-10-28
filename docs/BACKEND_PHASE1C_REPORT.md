# Backend Phase 1C hardening report

## Changes

- Added Ruff configuration (110 character line limit and E/F/W/I/UP/B/SIM rules), formatted the backend and scripts, and added Ruff and pytest-cov to the development requirements. Legacy compact statements and framework dependency defaults remain explicitly lint-ignored; Ruff still checks the remaining selected rules.
- Added a SQLite `rate_buckets` table in Alembic revision `0004_reconcile_legacy`. The HTTP middleware performs atomic per-minute upserts, so worker processes share counters. Added a test proving requests accumulate in the same SQLite bucket.
- Earlier API responses temporarily preserved a misspelled compatibility alias alongside `retrieval_score`; M3 R18 removes that alias from current responses and callers.
- Added prototype data export and cleanup in revision `0004_reconcile_legacy`: archived prototype tables are exported to `data/archive/legacy_export.json` under the configured data directory before the tables are dropped. The migration test upgrades a prototype database containing legacy rows and verifies the export and typed schema.
- Improved bundle generation with section and document outline entries, per-page labels that include bundle page and source document page, page rotation normalization, and an output page-count integrity check. Added a mixed-size, rotated two-page PDF test covering labels, rotations, page counts, download bytes, and Range.
- Added upload MIME validation and tests for oversized and unsupported uploads, duplicate uploads, OCR failure recovery, chunk page separation, RRF ordering, invalid citation foreign keys, shared rate buckets, and unsafe document paths.
- Made settings report the active database path and journal mode, and added a live model reachability field to AI settings.

Formatted files include `backend/alembic/`, `backend/app/`, `backend/tests/`, and `scripts/`. New tests are in `backend/tests/test_bundle_pdf.py`, `backend/tests/test_hardening_units.py`, and `backend/tests/test_ocr_recovery.py`; migration coverage is in `backend/tests/test_migrations.py`.

## Gates and verification

The requested Ruff commands passed:

```text
$ backend/.venv/bin/ruff check backend scripts
All checks passed!
$ backend/.venv/bin/ruff format --check backend scripts
51 files already formatted
```

The exact requested pytest-cov option `--cov-report=term-summary` is not supported by pytest-cov; pytest reports the accepted choices as `term`, `term-missing`, `annotate`, `html`, `xml`, `json`, `markdown`, `markdown-append`, and `lcov`. I ran the equivalent report command below. Exact final summary:

```text
$ .venv/bin/pytest -q --cov=app --cov-report=term-missing
24 passed in 83.78s (0:01:23)
TOTAL                                2420    779    68%
```

Coverage is 68%, short of the 85% target. The suite still lacks the requested exhaustive unauthenticated, role, validation, cross-owner, and happy-path matrix for every OpenAPI operation. Existing security tests cover representative cross-owner and role-denial cases, and new tests cover selected upload, file, and bundle cases. Lower-covered router areas include cases, drafts, strategy, settings, and community. This remains unfinished work.

Fresh empty-database migration and the prototype-row export path are covered by `backend/tests/test_migrations.py` in the passing suite. Revision `0004_reconcile_legacy` creates the rate bucket table as part of the same upgrade chain.

Live uvicorn smoke used `127.0.0.1:8010` with `TANTARA_DATA_DIR=/tmp/tantara-phase1c-live` and a scratch SQLite database. Verified:

```text
health 200 {'status': 'ok', 'service': 'TANTARA Local Workspace API', 'version': '1.1.0'}
login 200
dashboard 200
upload 202
job ready 1 None
hybrid search 200 1 [0.03278688524590164]
AI ask 200 ok Mumbai
LLM configured status {'provider': 'local', 'base_url': 'http://192.168.0.101:8080/v1', 'model': 'MiniCPM5-2B', 'reachable': True, 'latency_ms': 138}
generate 202 {'status': 'ready', 'pages': 5, ...}
download 200
pages 5 labels ['Bundle 1', 'Bundle 2', 'Bundle 3', 'Bundle 4', 'Bundle 5 · Phase1C Evidence source p. 1']
range 206 100 bytes 0-99/6088
```

The live test reached the configured local model and got a grounded answer, so the `model_unavailable` branch was not exercised live. No fallback answer was used.

Script runs used scratch data directories:

- `scripts/seed.py --demo`: seeded six clients, twelve cases, and four generated/indexed PDFs, then generated an eight-page bundle. The three remaining documents in the scratch database after the separate delete-index check were all marked `is_demo`.
- `scripts/seed.py --empty`: completed with zero chunks and a consistent empty vector index.
- `scripts/rebuild_index.py` run twice: both returned `{'chunks': 4, 'vectors': 4, 'consistent': True}`. After deleting one document, FTS rows dropped from four to three and rebuilding returned `{'chunks': 3, 'vectors': 3, 'consistent': True}`.
- `scripts/import_corpus.py`: completed and wrote the manifest. UNCITRAL was indexed. Wikisource was denied by its robots endpoint, LCIA disallowed the probe, India Code timed out, the Supreme Court and SIAC probes were unreachable, and the archive.org page had insufficient readable text. The manifest records those reasons, timestamps, source kinds, checksums, and license notes where applicable.

The repository's `backend/data` directory was not used for these script runs. All live and script scratch data was kept under `/tmp`.

## Remaining limitations

- Complete the requested per-route API matrix and raise application line coverage to at least 85%.
- Add a test that exercises `model_unavailable` explicitly with the configured model made unreachable.
- The lint configuration retains narrow ignores for pre-existing compact one-line statements, dependency defaults, and dynamic model imports; those patterns remain candidates for further cleanup.
- The import corpus manifest reports the reachability and robots restrictions observed at run time; failed sources require a later retrial from an allowed network.
