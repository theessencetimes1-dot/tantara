# M5 report

## M4 closeout at the start of M5

`reports/M4-report.md` is absent from the current tree. I re-read the M4 packet and the available `docs/INTEGRATION_REPORT.md`, then checked the pushed tip (`2cd0188`). The following status is based on the M4 packet's measured re-verification plus the current repository; all validation listed later in this report will be rerun as required.

| M4 row | Start-of-M5 status | Evidence or remaining work |
|---|---|---|
| R36/R50 README | Incomplete | README exists and has the project overview, diagrams, configuration and 14-module image table, but M5 requires the current API create status/query contract details and the comparison report link. |
| R45 duplicate module navigation | Completed | M4 packet reports `WorkspaceModuleNav` removed; M4 Playwright run passed; verify current `frontend/src` during M5. |
| R47 UI comparison | Completed, verify current citations | `docs/UI_COMPARISON.md` was committed with 14 module rows and target/actual capture paths; M5 requires the separate supplied draft to be verified and incorporated if coverage is missing. |
| R48 405 envelope | Completed | M4 verification measured `method_not_allowed`; keep in place. |
| R49 skip guards | Completed | M4 Playwright run passed 109 tests with no skips; verify test sources and run again. |
| R52 Research Desk synthesis | Completed | M4 verification measured `model_synthesis`, prose and citations; keep honest offline behavior. |
| R54 strategy reliability | Completed, suite-level proof pending | M4 packet reports 10/10 model-generated; M5 requires two consecutive full backend-suite runs. |
| R55/R56 clients navigation and mobile cards | Completed | M4 Playwright run passed the related navigation and mobile-card tests. |
| R57 Autofill date validation | Completed | M4 verification reports the probe passes valid/invalid date and skip behavior. |
| R58 one main landmark | Completed on primary routes; deep-link coverage incomplete | M4 removed the deeper route sweep after timeouts. Restore the coverage with content-based waits and preserve existing assertions. |
| R59 workspace timezone formatting | Implementation reported complete; acceptance incomplete | Shared formatter and consumer updates are in the tree, but the required cross-surface fixed-instant Playwright assertion remains to be verified or added. |
| R60 create status contract | Partially complete | Case creation returns 201 and collections use explicit route status; generic create handler still derives status from path, and README lacks per-endpoint create codes. |
| R61 screenshot corpus hygiene | Incomplete | Multiple screenshot corpora and unreferenced image assets remain. M5 will retain only referenced/current evidence, preserve design references, and report object-store size changes. |
| R62 formatting | Reported complete, verify | M4 says Prettier was fixed; rerun the exact M5 check. |
| R63 strategy validation warnings | Reported complete, verify | M4 packet reports the backend regression test passes and success responses retain `validation_warnings`; M5 full backend runs will verify. |
| R64 citation typecheck | Reported complete, verify | M4 packet reports `npx tsc --noEmit` exit 0; rerun. |
| R65 activity labels and actor | Incomplete | Humanize audit titles and resolve the actual `actor_id`, with a two-user regression test. |
| R66 README screenshot provenance | Incomplete | The last dashboard re-capture contains Playwright residue. Re-capture the README set from one pristine seeded directory after R65, with explicit hydration and fixture-residue guards. |
| R67 deterministic strategy test | M4 packet reports fixed; suite acceptance pending | M4 reports the formerly flaky test passed 10/10; M5 will run the full backend suite twice consecutively. |
| R68 empty-slug captures and ignores | Incomplete | Remove the 22 unreferenced dash-prefixed captures, guard the generator against an empty slug, and ignore future scratch directories. |
| R69 dashboard case table | Incomplete | The dashboard table's intrinsic width clips columns in its card; fix and verify geometry at 1440×900. |
| R70 deep-link landmark coverage | Incomplete | Restore the removed sweep with API-derived IDs and content-based waits; verify the required routes. |
| R71 draft scaffold honesty | Incomplete | A seeded, never-generated scaffold is presented as a failed model run. Distinguish scaffold provenance from actual failed generation and test both branches. |


## M5 completion evidence

### M4 rows completed during M5

The M4 report file was absent at the start of this pass. Its packet and the M4 measured re-verification were used to establish the start state above. Remaining M4 rows were completed as follows:

- **R36/R50/R47:** README now records API search query parameters and create status codes, links the per-module comparison, and documents the authenticated fresh-seed screenshot capture. `docs/UI_COMPARISON.md` records all fourteen target/actual pairs and preserves the target-reference framing and the four mock affordances not present in the product.
- **R58/R70:** restored a deep-link landmark sweep using IDs fetched from the API and waits for real page headings; it covers research library, strategy, client, document, bundle, and community routes.
- **R59:** cross-surface test compares one Community post timestamp and its Dashboard activity timestamp in the workspace zone.
- **R60:** create status is declared at route registration and documented in the README.
- **R61/R68:** one curated screenshot corpus remains; scratch locations are ignored and the capture tool rejects empty names and contaminated demo data.
- **R62/R64:** final Prettier and TypeScript checks pass.
- **R63/R67:** strategy validation warnings remain in the response and two consecutive full backend runs pass.
- **R65:** dashboard activity titles are human-readable and actor labels resolve from the event actor ID.
- **R66:** all 28 README screenshots were captured in one pass from a dedicated clean `--demo` database at 2026-10-28 20:43 UTC. The capture asserted 12 advocate cases, loaded metrics, no loading placeholders, and no known E2E fixture strings.
- **R69:** dashboard case table now fits its card; browser geometry assertions cover all headers and visible status chips.
- **R71:** untouched seeded drafts are labeled as template scaffolds; actual unrecognized generated text retains its warning branch.

The required M4 reports and probes were not available in the repository's `reports/` directory at M5 start. Current evidence is recorded below; no push or merge was requested in this packet.

### Validation outputs

Backend suite, two consecutive runs against the same final backend source:

```text
125 passed in 174.60s (0:02:54)
125 passed in 214.39s (0:03:34)
```

Frontend typecheck:

```text
$ cd frontend && npx tsc --noEmit
exit code: 0
```

Prettier:

```text
$ cd frontend && npx prettier --check 'src/**/*.{ts,tsx,css}' 'tests/**/*.ts'
Checking formatting...
All matched files use Prettier code style!
exit code: 0
```

Alembic:

```text
$ cd backend && python -m alembic heads
0010_collections (head)
```

Playwright against the single 8010/3010 stack, line reporter:

```text
112 passed (11.8m)
0 failed, 0 skipped
```

The suite started its managed web servers on the contract ports. The capture spec also passed against a separately seeded, pristine database and wrote 28 screenshots; every dashboard capture had the seeded count 12 and passed the residue guard.

Documentation and repository evidence:

```text
ALL REFERENCES RESOLVE
images that resolve: 28
tracked image files after cleanup: 37
curated docs/screenshots files: 28
```

`git count-objects -vH` before cleanup reported `size-pack: 90.35 MiB` and `size: 23.50 MiB` of loose objects. No history rewrite or repack was performed, so deletion commits do not immediately reduce the packed-object size; the committed tree now contains 37 images instead of 289.

### Files and behavior

The implementation touched backend activity presentation and create status registration; draft generation provenance; Dashboard table layout; draft scaffold presentation; API typings; Playwright coverage and screenshot output locations; README, issue ledger, UI comparison; capture tooling; `.gitignore`; 28 curated screenshots; and removal of unreferenced historical/scratch captures. Backend behavior changes were followed by both full backend runs above. All requested code and documentation references resolve in the final tree.
