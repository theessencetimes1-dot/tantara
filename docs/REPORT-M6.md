# M6 completion report

## M4 closeout status at M6 start

The repository's M5 report records the M4 closeout; `reports/M4-report.md` itself was absent. The M5 report says every M4 row below was completed, and I rechecked the current tree and validation relevant to this pass. No M4 row remains open.

| M4 rows | M5 evidence / current status |
|---|---|
| R36/R50/R47 README and UI comparison | M5 records the expanded README and 14-module comparison. M6 refreshed the image manifest and labels, and README links the comparison. The final link audit passes. |
| R45 duplicate module navigation | M5 records `WorkspaceModuleNav` removal and Playwright verification. M6 parity coverage confirms the rail label `Bundles`/`Strategy` alongside page headings `Filing Bundles`/`AI Strategy Advisor`. |
| R48 error envelope; R49 suite hygiene | M5 reports completed 405 envelope and no conditional API skips. M6 full Playwright gate passes with 112 tests. |
| R52 Research Desk synthesis; R54 strategy reliability | M5 reports model synthesis and 10/10 model-generated strategy. No changes were made to these behaviors in M6. |
| R55/R56 client navigation and mobile cards; R57 Autofill dates | M5 reports these verified. M6 full browser suite passes the route and mobile checks. |
| R58/R70 one-main landmark coverage | M5 restored the API-derived deep-link sweep. The M6 full Playwright run passes the sweep for research library, strategy, client, document, bundle, and Community thread. Community now renders the post and replies before waiting for ancillary identity/saved/case lookups. |
| R59 workspace timezone consistency | M5 reports shared formatter coverage and matching Community/Dashboard timestamp assertion. M6 screenshot capture uses the workspace timezone and checks the greeting date. |
| R60 create status contract | M5 reports explicit route status codes and README documentation. No M6 change was needed. |
| R61/R68 screenshot corpus and capture hygiene | M5 reports one curated corpus and ignored scratch folders. M6 refreshed all 28 retained images from a pristine seeded workspace; the image link/dimension audit passes. |
| R62/R64 formatting and citation types; R63/R67 strategy warning and determinism | M5 reports checks and backend suites green. M6 TypeScript and Prettier checks pass; backend suite passed with 131 tests. |
| R65 activity titles and actor | M5 reports human titles and actor lookup. M6 adds plural `drafts` normalization and regression cases for plural audit object names. |
| R66 README capture provenance | M5 refreshed all 28 screenshots from a clean seed. M6 adds explicit loading/PDF readiness and workspace-date checks, and refreshes the affected gallery files at one capture timestamp. |
| R69 dashboard case table; R71 draft scaffold honesty | M5 reports the geometry and scaffold behavior verified. M6 full Playwright passes the dashboard geometry and draft honesty checks. |

## M6 changes

- **R76 / R74 / R66:** the screenshot tool rejects any visible `Loading` text, waits for a rendered PDF canvas on desktop Documents, uses the configured workspace timezone, and checks the dashboard greeting date against the API's current workspace date. The authenticated screenshot tool now requires `TANTARA_E2E_PASSWORD`; it has no password default. A Node guard test covers loading rejection and the rendered-page requirement. All 28 README screenshots were recaptured in one pass from a dedicated fresh `--demo` data directory on 8010/3010. The 12-case census and forbidden test-fixture text guard passed. The README manifest is stamped `2026-10-28 22:04 UTC` for both viewports. I visually inspected `documents-1440x900.png`: the preview shows page 1 of the seeded arbitration agreement, including its rendered text, with no loading label.
- **R72:** `verify_bundles.py` now returns an honest `EMPTY WORKSPACE` verdict when the list is truly empty, and errors if an inconsistent response reports a nonzero total but no items. Existing populated-path checks remain. Both empty and populated verifier runs passed.
- **Activity copy:** added the missing plural `drafts` mapping and parametrized regression coverage for plural audit object names. The endpoint matrix tests and full backend suite pass.
- **R66 label consistency:** README, `docs/UI_COMPARISON.md`, and `ui-parity.spec.ts` distinguish the rail names `Bundles` and `Strategy` from the page headings `Filing Bundles` and `AI Strategy Advisor`.
- **Report references:** the pre-existing dangling screenshot references in the lane reports now identify the historical filename without creating a broken link when the image is outside the curated corpus. Existing image references continue to resolve; no historical files were recreated or linked to unrelated screenshots.
- **Deep-link resilience:** the Community thread publishes its core post/reply data before ancillary lookups, so a slow profile, saved-state, or case-name request cannot hold the discussion behind its loading state.

## Validation evidence

Backend suite, after activity-object changes:

```text
131 passed in 258.91s (0:04:18)
```

Frontend typecheck:

```text
$ cd frontend && npx tsc --noEmit
exit code: 0
```

Lint:

```text
$ cd frontend && pnpm lint
✔ No ESLint warnings or errors
exit code: 0
```

Prettier:

```text
$ cd frontend && npx prettier --check 'src/**/*.{ts,tsx,css}' 'tests/**/*.ts' scripts/capture-readme-screenshots.mjs scripts/capture-guards.mjs scripts/capture-guards.test.mjs
Checking formatting...
All matched files use Prettier code style!
exit code: 0
```

Capture readiness tests:

```text
ℹ tests 2
ℹ pass 2
ℹ fail 0
ℹ skipped 0
```

Full Playwright suite against the single 8010/3010 stack:

```text
112 passed (11.3m)
0 failed, 0 skipped
```

The first full run had one Community deep-link timeout while 111 tests passed. The focused route passed after the thread-load resilience change, and the subsequent full run above passed. No test was skipped or weakened.

Migration graph:

```text
$ /home/kahitoz/projects/tantara-wt/be/backend/.venv/bin/python -m alembic heads
0010_collections (head)
```

Bundled verifier, empty workspace:

```text
advocate bundles: total=0 items=0 keys=none
EMPTY WORKSPACE: advocate bundles total=0, items=0; populated bundle checks not applicable.
```

Bundled verifier, seeded workspace:

```text
ALL BUNDLE DETAIL/PREVIEW/DOWNLOAD EXPECTATIONS PASSED
```

Documentation audit:

```text
docs audited: 27 files, 31 relative references
images that resolve: 28
ALL REFERENCES RESOLVE
```

The separate lane-report image audit checked the remaining path citations and found 0 missing. The screenshot capture refusal path was also checked with `TANTARA_E2E_PASSWORD` unset; it exits nonzero with a clear message and does not print or persist a credential.

## Remaining work

No M6 packet item remains open. The full `pnpm build` was not part of the requested M6 validation and was not run.
