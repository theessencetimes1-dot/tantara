# Open issues and verification notes

No M5 acceptance finding remains open at the verified commit. The M5 closeout is recorded in `reports/M5-report.md`; the M4 closeout evidence is summarized at the top of that report because `reports/M4-report.md` was not present in the starting tree.

## Recently verified findings

| Finding | Verification evidence |
|---|---|
| R59 — timestamp display disagreed by module | `workspaceDateTimeDisplay` formats Community, Dashboard, Drafts, Bundles, and Strategy in the configured workspace zone; the `community post and its dashboard activity use the same workspace wall clock` Playwright case compares the same new post/activity instant and requires identical displayed text. |
| R60 — creation status was inferred in handler logic | Domain create routes now receive the declared `CREATE_STATUS_CODES` value at route registration; the README API table lists the create endpoint status contract. Full backend suite: 125 passed in 214.39s. |
| R61/R68 — screenshot corpora and empty-slug artifacts | `docs/screenshots/` contains only the 28 README captures; other historical capture directories and unused images were removed. The capture script rejects empty slugs and contaminated data, and `.gitignore` excludes capture scratch directories. |
| R65 — dashboard activity labels and actor | The dashboard resolves each actor from `AuditEvent.actor_id` and maps known action/object names to readable titles. `test_dashboard_activity_humanizes_audit_rows_and_uses_the_stored_actor` checks a researcher actor in an advocate feed. |
| R66 — README captures included test residue or loading state | `frontend/scripts/capture-readme-screenshots.mjs` uses the dedicated demo-seeded API, requires exactly 12 advocate cases and hydrated dashboard metrics, and rejects known test-fixture strings before saving. All 28 images were captured in one pass at the recorded UTC time. |
| R69 — dashboard case table clipped its contents | Compact case table and status tabs wrap within their card; `dashboard case table headers remain separate at desktop width` checks table and tab widths, header bounds, and visible status chips. |
| R70 — deep routes lacked a main-landmark sweep | `deep-linked workspace routes retain one main landmark after real content loads` covers the Research library, case Strategy, client profile, document viewer, bundle detail, and Community thread using API-derived IDs. |
| R71 — untouched seeded draft was labelled as a failed generation | Draft detail derives generation provenance from saved version notes; the seeded scaffold and generated unstructured draft branches are both asserted in `drafts-unavailable-capture.spec.ts`. |

## Tooling and validation notes

- The external style-contract helper previously reported `auth_present: false` and no login request. Its unauthenticated style output is not evidence about authenticated routes.
- A former verifier strategy-write probe used the wrong HTTP method and returned 405; authorization is instead covered by `frontend/tests/api-domain-contracts.spec.ts`.
- The former authorization-test skip was removed. The browser suite is run with no skipped tests; ownership behavior is covered by the second seeded identity.
- The calendar hook dependency warning was corrected; the checked frontend lint command emits no warning for that file.

The full Playwright suite at M5 verification ran 112 tests with 112 passed, 0 failed, and 0 skipped. The backend suite passed twice consecutively (125 tests on each run). The full test transcripts and other validation outputs are in `reports/M5-report.md`.
