# Backend Phase 6 report

## Changes

- Added a researcher login (`researcher@tantara.local`) to the demo workspace. It shares the configured local demo password with `advocate@tantara.local`, has a distinct `researcher` role, and owns a demo client, case, indexed document, task, hearing, draft, bundle, community post, and reply. All owned demo records are marked `is_demo`. The seed reconciles an existing advocate demo without duplicating its corpus.
- Added a generated HTTP method inventory from `backend/openapi.json`: 80 paths and 123 method/path operations. `scripts/write_route_inventory.py` regenerates `docs/BACKEND_ROUTES.txt` and expands the method-level table in `docs/TEST_MATRIX.md`. A test checks the generated inventory and matrix against OpenAPI.
- Moved semantic relevance filtering after RRF fusion. Lexical matches are retained; semantic-only fused hits below cosine similarity `0.35` are removed. No-match results have `items: []` and `total: 0`.
- Replaced the obsolete `app/rag.py` global search/Anthropic path with owner-scoped hybrid retrieval and the configured local model caller. Missing evidence, unavailable embeddings, and unavailable model results stay distinct. Model unavailability has no model attribution or generated answer text.
- Changed the Ask outage explanation so an empty citation list does not claim documents were found. M3 R17 now retains retrieved citations and supports if generation is unavailable while returning a neutral outage explanation and no model attribution; M3 R18 exposes canonical `retrieval_score` only.

## Verification

Commands ran from `backend/`, with a scratch `TANTARA_DATA_DIR` and explicit `DATABASE_URL`:

```text
.venv/bin/ruff check . ../scripts
All checks passed!

.venv/bin/ruff format --check . ../scripts
63 files already formatted

scratch=$(mktemp -d)
TANTARA_DATA_DIR="$scratch" DATABASE_URL="sqlite:///$scratch/test.db" .venv/bin/pytest -q
76 passed in 180.38s (0:03:00)
```

The full suite includes `test_all_protected_openapi_operations_reject_anonymous_requests` (each protected HTTP method), `test_all_openapi_mutation_bodies_return_validation_envelope` (body-bearing POST/PUT/PATCH operations), existing owner CRUD and resource scoping cases, and `test_generated_method_inventory_covers_every_openapi_operation`. The matrix distinguishes operations with no request body from validation-bearing mutations.

New direct tests in `tests/test_rag_security_round6.py` cover RRF scoring/order, post-fusion semantic padding removal, no-evidence retrieval, embedding degradation, the page-and-score citation shape, password hashing, signed-token expiry and tampering, and credential non-disclosure. The updated ranking assertions in `test_demo_seed_has_multpage_content_calendar_extractions_and_feed` cover the exact page-three phrase, the semantic query “where will the tribunal sit,” a single-document marker, force-majeure partial results, query-sensitive top-three sets, ordinary unrelated text, and `zzyz quuxorp plinth` returning zero results.

The dead-model HTTP tests set the per-user model URL to `http://127.0.0.1:9/v1`, assert `/settings/ai` and `/ai/status` report `reachable: false`, and guard socket connections so only that configured loopback destination is attempted. Ask returns `status: model_unavailable`, `model: null`, `citations: []`, and the message “The search could not be completed because the configured language model is unavailable.” The prior wording said relevant documents were found despite returning no citations. Session Ask shares that response. Drafts returns an explicitly labelled review template; AI Read returns `local_extraction`; Autofill returns `record_based`; Strategy returns a `template`/`excerpt_listing`. These last three are record/text extraction surfaces and do not call the language model. No community-assistance generation route exists in this OpenAPI contract. The reachable local model success test remains green.

## Seed counts

The real `scripts/seed.py --demo` run in a fresh scratch workspace reported 7 advocate clients, 12 advocate cases, and 8 advocate PDFs. SQL totals including the researcher-owned demo records were:

| Table | Rows |
|---|---:|
| users | 3 |
| clients | 8 |
| cases | 13 |
| documents | 9 |
| document_pages | 45 |
| document_chunks | 44 |
| tasks | 18 |
| hearings | 10 |
| drafts | 2 |
| filing_bundles | 2 |
| community_posts | 6 |
| community_replies | 9 |
| case_events | 60 |
| extraction_fields | 16 |

The original advocate seed remains 7 clients, 12 cases, 8 documents, 40 source pages, 17 tasks, 9 hearings, 1 draft, 1 bundle, and 5 posts. The additional researcher matter contributes 1 client, 1 case, 1 five-page document (5 chunks), 1 task, 1 hearing, 1 draft, 1 bundle, 1 post, and 1 reply.

## Live HTTP isolation probe

Started and stopped uvicorn on `127.0.0.1:8129`, against the same scratch-seeded workspace. The HTTP probe logged in as both local demo users and observed:

```json
{
  "users": {"advocate": 8, "researcher": 1},
  "cases": {"advocate": 12, "researcher": 1},
  "clients": {"advocate": 7, "researcher": 1, "researcher_case_count": 1},
  "foreign_ids": {
    "document_get": 404, "document_patch": 403,
    "case_get": 404, "case_patch": 403,
    "client_get": 404, "client_patch": 403
  },
  "dashboard_active_cases": {"advocate": 10, "researcher": 1},
  "researcher_search_hit_count": 5,
  "foreign_community_replies_status": 404
}
```

The researcher calendar contained no advocate case title, and every researcher search hit referenced the researcher-owned document. No request bound to `0.0.0.0`; the server was stopped after the probe.

## Remaining scope notes

- HTTP 422 validation is meaningful for operations with request bodies and query/path constraints; bodyless DELETE operations have no malformed request body to validate. The method matrix marks those cells accordingly.
- `settings/ai` reachability is checked by the existing runtime probe and the closed-port test. It is a point-in-time connection check, not a persistent model-health guarantee.
- Coverage was not rerun for this round; the requested verification here was the full pytest suite, lint/format, seed, and live isolation probe.

## Commits

Each changed file is committed separately; no push or merge was performed.

- `19d192f` — `backend/app/services/retrieval.py`
- `68846c6` — `backend/app/main.py`
- `88a2f78` — `backend/app/rag.py`
- `8ab8fd3` — `backend/tests/test_ai_degradation.py`
- `2fd53d0` — `backend/tests/test_contract_stability.py`
- `160b4b0` — `backend/tests/test_workflows_cde.py`
- `b5ecf19` — `backend/tests/test_workspace_round4.py`
- `6f96cf8` — `backend/tests/test_rag_security_round6.py`
- `6eef415` — `scripts/seed.py`
- `b9d6e0a` — `scripts/write_route_inventory.py`
- `eca6cbc` — `docs/BACKEND_API.md`
- `e11749a` — `docs/TEST_MATRIX.md`
- `ae5e9ba` — `docs/BACKEND_ROUTES.txt`
- `f29f34b` — `backend/README.md`
- `docs/BACKEND_PHASE6_REPORT.md` — final report commit
