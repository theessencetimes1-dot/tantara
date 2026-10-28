# Integration report

Branch: `feat/tantara-workspace`
Implementation HEAD validated: `843ada7` (`Wait for strategy mobile navigation and assert tabs`).
The two final semantic-nav commits are `1d1ba9f` and `843ada7`; both are pushed to `origin/feat/tantara-workspace`.

## Lane merge record

The eight lane branches were reported at `ahead=0`; their origin SHAs were:

| Lane | `origin/<branch>` |
|---|---|
| be | `3a4dacb` |
| fe | `983f8b4` |
| fe2 | `203d28f` |
| fe3 | `2121281` |
| fe4 | `eb85b22` |
| fe5 | `20d4693` |
| fe6 | `ec30a01` |
| fe7 | `1042b26` |

Merge commits: `324f718` backend-core, `5c5a7c4` frontend-core, `b5549eb` frontend-cases, `3d32f80` frontend-documents, `b058b3f` frontend-research, `b771771` frontend-drafts, `ced42d7` frontend-bundles/strategy, `0b07a31` frontend-community.

### Material conflict resolutions

- Kept the 937-line Research Desk implementation and carried the bundles lane's “open evidence in Research Desk” follow-up into it.
- Kept core's 1,271-line `globals.css` and self-hosted fonts; rejected the Google-font layout variant.
- Kept the 425-line cases shell and merged the union navigation for dashboard, cases, documents, research, drafts, bundles, calendar, tasks, clients, community, settings, autofill, strategy, and search.
- Preserved the concrete workspace `allowBuilds` settings, removed the temporary shooting script and API-fixture files, and eliminated `page.route()` shims from tests.
- Reviewed and adopted the useful fe5 draft-editor output and fe6 filing-bundle/paperbook work; screenshots in the repository are authentic browser captures, not fixture captures.

Three pre-existing evidence commits were preserved without rewriting: `d4aa6f7`, `85e0a87`, and `4e71023` were authored by `theessencetimes1-dot <theessencetimes1@gmail.com>`. All commits made for this closeout used `Cynthia1122 <cynthiamodonca09@gmail.com>`.

## Validation

Full Playwright suite, real seeded backend, API on `127.0.0.1:8010`, frontend on `127.0.0.1:3010`:

```text
  1 skipped
  102 passed (10.1m)
playwright_exit=0
```

The one skip is the existing cross-user client/task/calendar test, which requires a second seeded identity. The focused bundle/strategy file also passed after the semantic fixes:

```text
  11 passed (2.4m)
```

Backend coverage from the current exact integration-script run:

```text
TOTAL                                3109    225    93%
104 passed in 376.17s (0:06:16)
```

Frontend gates from the current exact integration-script run:

```text
pnpm install                                   0
$ prettier --check "src/**/*.{ts,tsx,css}" tests
Checking formatting...
All matched files use Prettier code style!
pnpm lint                                      0
tsc --noEmit                                   0
○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
pnpm build                                     0
```

The earlier direct command `pnpm exec tsc --noEmit` exited 0 with no output. Lint/build report the existing React hook dependency warning in `frontend/src/features/calendar/index.tsx:137` for `cursorParts.month` and `.year`; both gates exit 0.

## Current exact `verify_integration.sh` run

Command (the supplied script was unmodified):

```text
BEPORT=8194 FEPORT=3034 BE_VENV=/home/kahitoz/projects/tantara/backend/.venv TANTARA_API_ORIGIN=http://127.0.0.1:8010 TANTARA_API_PORT=8010 TANTARA_WEB_URL=http://127.0.0.1:3010 TANTARA_WEB_PORT=3010 bash /home/kahitoz/projects/tantara-run/review-tools/verify_integration.sh
```

The outer verifier probes used the isolated API/frontend at 8194/3034; its Playwright config started one seeded API/frontend pair at 8010/3010. Exact output excerpts:

```text
alembic upgrade head                           0
seed --demo                                    0
TOTAL                                3109    225    93%
104 passed in 376.17s (0:06:16)
GET /api/v1/cases                              200
GET /api/v1/clients                            200
GET /api/v1/tasks                              200
GET /api/v1/documents                          200
GET /api/v1/drafts                             200
GET /api/v1/bundles                            200
GET /api/v1/community/posts                    200
GET /api/v1/search/documents                   422
ALL BUNDLE DETAIL/PREVIEW/DOWNLOAD EXPECTATIONS PASSED
ALL DRAFT VERSIONING/RESTORE/EXPORT EXPECTATIONS PASSED
ALL QUERY/ANSWER-GROUNDING EXPECTATIONS PASSED
alembic upgrade head on the copied dir         0
seeded bundle download after relocation        200 71557B magic=%PDF
pnpm lint                                      0
tsc --noEmit                                   0
pnpm build                                     0
host:port literals in src?                     0
tantara_preview refs (src/tests, must be 0/0)? 0/0
  /autofill -> 200
  /bundles -> 200
  /calendar -> 200
  /cases -> 200
  /clients -> 200
  /community -> 200
  /dashboard -> 200
  /documents -> 200
  /drafts -> 200
  /research -> 200
  /search -> 200
  /settings/profile -> 200
  /strategy -> 200
  /tasks -> 200
nav broken entries: NONE
style contract                                 INVALID (rc=1, unauthenticated run — no UI findings recorded)
playwright suite (real backend, no shims)        1 skipped   102 passed (9.7m)
exact_current_verify_exit=0
```

The standalone `Terminated` line is emitted while the script stops its background uvicorn child during data-relocation cleanup; the same transcript then continues through frontend quality gates and Playwright. The outer shell returned exit 0 (`exact_current_verify_exit=0`). Its fixture-count label prints `<no value>` before the separate zero count because a display-only `res` call still omits its second value. The script's `researcher strategy write` probe returned HTTP 405, so that particular probe does not establish an authorization result.

An earlier exact run, before the external helper was repaired, stopped at:

```text
/home/kahitoz/projects/tantara-run/review-tools/verify_integration.sh: line 19: $2: unbound variable
verify_integration_exit=1
```

That was an external script defect; the current exact run above is the later result after the helper gained a default argument. No external review-tool files were modified by this repository work.

## UI evidence

The exact target probe returned:

```text
docs/design/frontend.png: 1536x1024 sidebar_w=222 sidebar_bg=#031023 header_h=70 workspace_bg=#FDFDFD primary=#EDF7F6 gold_px=2588 nav_rows~25
```

Fresh, test-free seeded captures are committed in `docs/screenshots/`: 14 desktop screenshots at 1440×900 and 14 mobile screenshots at 390×844, covering all workspace modules. The 11 requested routes were covered by `ui_compare.mjs`; `/autofill`, `/search`, and `/strategy` have supplementary authenticated captures. Captures assert an authenticated session and mobile `scrollWidth <= 390`. No fixture-named screenshots remain.

The separate `style_contract.mjs` attempt used the main-repository server at 3034 but did not authenticate:

```text
form_without_method: null
auth_present: false | login_call: no-login-request-seen | url: http://127.0.0.1:3034/
INVALID: no authenticated session — unauthenticated route diagnostics are not UI findings and must not be reported as defects.
```

Its subsequent unauthed heading/style diagnostics are invalid. The authenticated screenshot/browser checks and Playwright assertions are the UI evidence for this report.
