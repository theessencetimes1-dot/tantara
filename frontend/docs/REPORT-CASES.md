# Cases / Clients / Tasks / Calendar — Round 3

## Round 4 acceptance follow-up

This section supersedes Round 3's statement that the seeded Cases collection did not expose a hearing projection. The private API's `GET /cases` response does include `next_hearing_at`, derived as the earliest hearing whose `at` value is at or after the API clock. The Round 3 UI overlaid a hearings collection map, which admitted past dates and made the list disagree with case detail. Round 4 removes that map and uses the case API projection in both views.

### Sol-ranked findings

| Finding | Round 4 change | Test/evidence |
|---|---|---|
| Next.js “N” dev badge contaminated screenshots. | Added `devIndicators: false`; capture checks the indicator element and visible issues badge in the Next shadow portal before every screenshot. | `pnpm screenshots` passed with no visible indicator in the 16 recaptured states. |
| Cases mobile hid hearing/status columns and clipped status tabs. | Added responsive case cards with title, forum, next hearing and status; kept status tabs horizontally accessible and removed the table's hidden mobile columns. | E2E verifies a card and its status/hearing values fit within the 390px viewport; 360/390/768/1024/1440 route smoke passed without horizontal overflow. |
| Calendar mobile month view was unreadable. | Calendar switches to Agenda below 650px; agenda rows retain normal wrapping and full event text. The Month view remains available on desktop. | E2E verifies Agenda is selected at 390px, event labels do not use word-breaking styles, and the document has no horizontal overflow. Capture shows dated agenda groups. |
| Next hearing values were stale/inconsistent. | Removed client-side hearing map; list and detail format the same API-derived `next_hearing_at`. Rows with no future hearing retain `—`. | API-level regression compares projection to the minimum future linked hearing, asserts no returned projection is earlier than the test clock, then verifies the same date in list and detail. |
| Client zero-case count was shown as unavailable. | Kept the API's computed `case_count` value intact, including numeric zero. Missing/null remains `—`. | API + UI test finds the seeded zero-case client and asserts its Cases cell reads `0`. |
| Task Retry had no recovery proof. | Added a visible Retry button with focus-ring styling. Empty task groups are omitted; task rows now use title, due, priority and linked-case columns. | E2E forces the first two browser task fetch attempts to fail, clicks Retry, then verifies real API task groups replace the error state. |
| Task list showed empty groups and had low information density. | Only populated groups render; task rows use a compact column grid and stronger priority styling. | E2E smoke and loaded task capture. |
| Cases list had excess row height and filtered searches said “No matters yet.” | Removed duplicated demo labels from each row (the global honest sample-data badge remains); reduced cell padding and added “No matching cases.” | Loaded and empty case captures; route smoke. |
| Active route state needed proof for Calendar and case detail. | Existing shell route-prefix matching now has explicit coverage for Cases, case detail, Clients, Tasks and Calendar. | E2E asserts exactly one `aria-current="page"` link on each route. No shell behavior was changed this round. |

### Current capture inventory

- `docs/screenshots/cases-desktop.png` — clean seeded 12-case list, real counts and future hearing projections.
- `docs/screenshots/cases-mobile.png` — 390px responsive case cards with status and hearing visible.
- `docs/screenshots/case-detail-desktop.png` — seeded case detail with API-derived next hearing.
- `docs/screenshots/clients-desktop.png` — seeded clients, including the genuine zero-case client.
- `docs/screenshots/tasks-desktop.png` — populated task groups with due dates, priorities and case links.
- `docs/screenshots/calendar-desktop.png` — seeded October month view.
- `docs/screenshots/calendar-mobile.png` — 390px agenda with dated event groups.
- `docs/screenshots/dashboard-desktop.png` — dashboard with the existing Matters card and metrics.
- `docs/screenshots/cases-empty.png`, `clients-empty.png`, `calendar-empty.png` — genuine empty search/period states.
- `docs/screenshots/cases-failure.png`, `clients-failure.png`, `tasks-failure.png`, `calendar-failure.png`, `case-detail-failure.png` — API failure states with retry treatment.

### Gates

- Previous E2E baseline: 20 tests. Round 4: `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm test:e2e` — **25 passed**.
- `pnpm format` — passed.
- `pnpm lint` — passed; no ESLint warnings or errors (Next reports `next lint` is deprecated).
- `pnpm typecheck` — passed.
- `pnpm build` — passed; 17 app routes generated.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm screenshots` — passed; 8 loaded real-data captures, 3 genuine empty states and 5 failure states. Captures used a fresh temporary SQLite database seeded with `scripts/seed.py --demo` and the required `DATABASE_URL`.

### Remaining gaps

- The sidebar art still uses the existing illustrated SVG rather than the target's photographic scales-and-books image. The repository has no photographic sidebar asset; the N badge was removed from captures via configuration, but the photo fidelity itself remains open.
- Team assignment, case Research and case Activity log remain unavailable for the backend reasons documented above. Client edit/delete/status CRUD and dedicated keyboard tests for every dialog remain open.
- No behavior in `src/components/shell.tsx` changed in Round 4; integration still needs to retain the previously documented Round 3 shell behavior when reconciling with `frontend-core`.

### Round 4 commits

Each implementation, test, screenshot and report path was committed separately; no push or merge was performed.

- Config: `af7bfbc`.
- Case detail: `c909156`; Calendar mobile: `1352261`; case list: `adf5d29`.
- Feature styles: `6648315`; Tasks: `2bc53a7`.
- Capture guard: `8999f57`; acceptance tests: `9fced7d`, `e407cd8`.
- Screenshots each have an individual `Refresh <filename> evidence` commit; see the filenames above and `git log` for their current commit IDs.
- This report is committed separately after its contents are finalized.

## Sol-3 defect follow-up

| Finding | Fix | Files | Evidence |
|---|---|---|---|
| Unconditional unread dot claimed notifications without evidence. | Removed the fixed dot. The bell is labelled “Recent activity”; the API exposes no unread-count field, so the activity bell has no dot. | `src/components/shell.tsx`, `src/features/shell/styles.css`, `tests/cases-regressions.spec.ts` | `shell has no activity signal when the real activity feed is empty` reads the real feed and asserts `.activity-dot` is absent. |
| Header originally used a hard-coded identity fallback. | Identity begins empty; loading uses “Signing in…” and a neutral initials box; auth failure displays “Signed out” / “Authentication unavailable” and the app shows a sign-in treatment. Preview has a neutral “Preview workspace” label. | `src/components/shell.tsx`, `tests/cases-regressions.spec.ts` | `shell renders identity from the signed-in account`. |
| Next Hearing was blank despite seven seeded hearings. | `/cases` has no computed hearing projection; the case model's `next_hearing_at` is nullable and all seeded cases return null. The table now makes one bounded `GET /hearings?page=1&page_size=100&sort=at` request and maps the nearest hearing by `case_id`. | `src/features/cases/api.ts`, `src/features/cases/components/case-list.tsx`, `tests/cases-regressions.spec.ts` | Direct API read on the isolated seed: `/cases` returned 12 records and `next_hearing_at: null` for each; `/hearings` returned 7, including a hearing linked to `ABC Pvt. Ltd. vs. XYZ Ltd.` at `2026-10-28T10:00:00`. Regression asserts both API facts and the rendered date for a linked case. This is one collection call, not N+1. |
| Shell was one-line, inline-styled, and omitted lane navigation. | Reformatted shell, moved its shell-specific styling to a feature stylesheet, and added active navigation links in target order for Dashboard, My Cases, Research Desk, Drafts & Documents, Calendar, Tasks, Clients, Community, and Settings. | `src/components/shell.tsx`, `src/features/shell/styles.css`, `package.json` | `pnpm format`, route smoke, and rendered shell regressions pass. |

## Continued feature work

- Tasks now support create and edit with title, case link, due date/time, priority, status, and notes; completion remains optimistic with rollback on API failure. Uses `POST /tasks` and `PATCH /tasks/{id}`.
- Case detail now has create/edit/delete flows for timeline events, hearings, participants (including counsel role), and notes, using the corresponding supported endpoints. Notes, documents, and drafts use their real filtered listing endpoints.
- Case detail retains explicit unavailable states for case-specific Research and the Activity log because this backend exposes neither a case research listing nor an audit/activity listing endpoint. It does not refetch the case record for those tabs.
- The API has no assigned-team/team-member field or assignment endpoint on Case. Counsel participants can be recorded as case participants, but this is not a substitute for an assigned-team feature. Case form team assignment remains open.
- Shell changes are intentionally explicit for integration to port onto `frontend-core`'s authoritative shell. In `src/components/shell.tsx`, the nav array/order is at line 30; empty identity/auth error state starts at lines 52–54 and auth resolution at 76–98; real activity fetch is at 159–166 and the conditional signal at 285–294; neutral avatar and loading/signed-out labels are at 317–361. `src/features/shell/styles.css` owns the former inline shell layout styles. The file is much larger in this branch because Prettier expanded its original one-line statements; the behavioral port is the nav, activity signal, and identity/auth handling described above. Integration must reconcile these behaviors with `frontend-core`'s shell.

## Screenshots

All captures below use a clean, isolated demo seed on `127.0.0.1:8112`; loaded records are real API responses and demo records are marked in the UI.

- `docs/screenshots/cases-desktop.png` — seeded cases table, live counts, hearing dates, pagination.
- `docs/screenshots/cases-mobile.png` — seeded cases table at 390px.
- `docs/screenshots/case-detail-desktop.png` — seeded case overview and real case facts.
- `docs/screenshots/clients-desktop.png` — seeded client directory.
- `docs/screenshots/tasks-desktop.png` — seeded task groups.
- `docs/screenshots/calendar-desktop.png` — seeded calendar month.
- `docs/screenshots/calendar-mobile.png` — calendar at 390px.
- `docs/screenshots/dashboard-desktop.png` — dashboard with Matters card below the existing metrics.
- `docs/screenshots/cases-empty.png` — real search with no matching cases.
- `docs/screenshots/clients-empty.png` — real search with no matching clients.
- `docs/screenshots/calendar-empty.png` — real event-free agenda period.
- `docs/screenshots/case-detail-failure.png` — case API failure with retry treatment.
- `docs/screenshots/cases-failure.png` — case API failure with Retry.
- `docs/screenshots/clients-failure.png` — client API failure with Retry.
- `docs/screenshots/tasks-failure.png` — task API failure with Retry.
- `docs/screenshots/calendar-failure.png` — calendar API failure with Retry.

## Quality gates

- Before this round: 17 Playwright tests passed.
- After this round: `pnpm test:e2e` — 20 passed. The three added tests cover empty recent activity/no dot, neutral auth-loading identity, and the API/UI next-hearing projection.
- `pnpm format` — passed.
- `pnpm lint` — passed, no ESLint warnings or errors.
- `pnpm typecheck` — passed.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm build` — passed for all app routes.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm screenshots` — passed, saving 8 loaded real-data captures, 3 genuine empty states, and 5 API-failure states. The earlier clean-seed capture also passed before final case editor CRUD wiring; these screenshot surfaces do not include those editor dialogs.

## Remaining work

- Case team assignment needs a real backend field and endpoint; current case participant CRUD can record counsel roles but cannot assign workspace team members.
- Case Research and Activity log remain unavailable because their listing endpoints are absent.
- Client directory remains short of full edit/delete/status CRUD.
- Dedicated keyboard assertions for the dialogs and E2E CRUD coverage for the new event/hearing/note edit/delete controls are still missing.

## Commits

One file per commit; no push or merge was performed.

- Shell formatting script: `e4c7ba9`
- Shell behavior: `64d452c`
- Shell feature styles: `7a836e6`
- Case API wrappers: `7b63111`
- Next-hearing projection: `ea66f75`
- Case/task styles: `ab8aa9c`
- Task editing: `a032f9b`
- Case detail resources/editors: `c11d4d3`
- Defect regressions: `898fc59`
- Screenshots, in the order listed above: `2be79f6`, `5ad025e`, `1d80ff6`, `c55c380`, `d86c74e`, `ac29790`, `7d41534`, `8f09820`, `7b230a3`, `8c6a50e`, `bb5602d`, `1760599`, `00a5a06`, `aae675b`, `93b91f4`, `653797f`.
- This report is committed separately after the listed implementation and capture commits.
# Round 5 — API-backed case, calendar, client and task evidence

This section is the current Round 5 record and supersedes earlier historical statements below where they conflict. In particular, hearing dates come from the backend's `next_hearing_at` projection; there is no client-side hearing map. Screenshots listed here were regenerated against a freshly migrated/seeded backend at `127.0.0.1:8112` and the frontend at `localhost:3012`.

## Sol L3d findings

| Finding | Change and file | Test/capture assertion |
|---|---|---|
| Cases screenshots lacked real API proof and showed “Sample workspace data.” | Removed that placeholder from `src/features/cases/components/case-list.tsx`. `tests/capture-owned-routes.mjs` reads the sorted first page from `GET /api/v1/cases?page=1&page_size=20&sort=-updated_at`, verifies the first rendered desktop row or mobile card has the same title, and rejects the placeholder in captured copy. | Capture run fails unless the rendered first row matches the live API response. `cases-desktop_1440x900_loaded.png` and `cases-mobile_390x844_loaded.png` show the same top row as the API. |
| Next hearing needed one proven value across list, detail and calendar. | Kept the backend-derived `next_hearing_at` as the only list/detail source. The capture harness checks the selected case projection against `GET /hearings`, then checks `GET /calendar` contains that exact hearing. | `case API projects the earliest future hearing and the list renders it` asserts the projection matches the earliest future hearing, the list and detail show the same date, and a selected calendar event shows that date and linked case. It selects a next-month future hearing so it can be shown in all three views. |
| Raw calendar enum values and times leaked for all-day events. | `src/features/calendar/index.tsx` maps enum titles to human labels, renders all-day events without a `<time>` element, and formats selected-event dates consistently with the case list. | `calendar labels all-day events without a time or raw event enums` asserts the API-backed all-day row has no time element, its detail is marked All-day with no clock value, and the page contains none of `all_day_event`, `first_hearing`, or `hearing_completed`. |
| Mobile calendar was long and repetitive without a selected-event detail. | Calendar Agenda groups events by date, shows at most seven eventful day groups per page, adds Previous/Next days controls when needed, and opens a selected event detail panel. The detail panel is fixed inside the mobile viewport. | `calendar mobile defaults to readable agenda view` reads `GET /calendar`, derives the number of event dates, asserts at most seven day groups, and checks that Next days changes the page when the API has more than seven dated groups. It checks no mobile overflow, no word-splitting, and opens event details. Capture `calendar-mobile_390x844_selected-event.png` shows selection. |
| Tasks route needed the nine-item navigation and one active route. | No shell edit this round; the existing nine-item nav stays intact. | `case, calendar and client routes each expose one active navigation link` loops Cases, case detail, Clients, Tasks and Calendar and asserts exactly one `aria-current="page"` plus all nine nav links. |
| Client retry copy ran into its action. | `src/features/clients/client-directory.tsx` separates the error message from a styled Retry button. | Capture harness fails the first two client requests, clicks Retry, then waits for a real `GET /api/v1/clients` row before saving `clients-desktop_1440x900_retry-success.png`. |
| Tasks needed populated evidence and an equivalent mobile row action. | `src/features/tasks/index.tsx` resolves linked case names with a real `GET /api/v1/cases?page_size=100` request (the old generic linked-case fallback came from passing query syntax into the endpoint wrapper). Added a mobile-visible action menu for Edit and completion. | `mobile task actions remain available and open a labelled menu` asserts the task has real linked-case context and the mobile actions open. `tasks-desktop_1440x900_loaded.png` shows task groups, due dates, priorities, completion controls and case links; `tasks-mobile_390x844_action-menu.png` shows the mobile action menu. |
| Repeated task titles needed context. | Same real case-title lookup in `src/features/tasks/index.tsx`; task titles remain API values and linked case names appear in a separate column. | The populated Tasks captures show repeated “Review pleadings and evidence” tasks paired with different API case titles; no task titles are fabricated. |

## API contract coverage

`tests/api-domain-contracts.spec.ts` exercises the seeded API directly:

- `GET /calendar` returns an event array; malformed `from` dates return an error status.
- `GET /clients` succeeds; a unique no-match query returns an empty `items` list; invalid `POST /clients` returns 422; valid creation succeeds; `GET /clients/{cid}/cases` returns an empty list for a newly created client.
- `GET /tasks` succeeds; page 999999 returns empty `items`; invalid `POST /tasks` returns 422; valid creation and `GET /tasks/{rid}` succeed; `PATCH /tasks/{rid}` persists a priority change.
- Anonymous reads for calendar, tasks, clients, client cases and task detail, plus anonymous client/task creation and task patch, return 401.
- Cross-user access remains unproven. The test is explicitly skipped because `API-GOTCHAS.md` records that the current seed creates one user; it is ready to enable once the backend seed provisions a second user.

## Round 5 captures

All files below are exact viewport captures, use real seeded API data except the stated error injection, and have no loading skeleton or visible Next dev badge. The `-fixture` suffix is not used because these captures are not fixture-backed.

| File | Viewport and state | API source |
|---|---|---|
| `docs/screenshots/cases-desktop_1440x900_loaded.png` | 1440×900, loaded cases table and live counts | `GET /api/v1/cases?page=1&page_size=20&sort=-updated_at` plus live status-count queries |
| `docs/screenshots/cases-mobile_390x844_loaded.png` | 390×844, loaded case cards with title, status and hearing field | Same sorted `GET /api/v1/cases` list |
| `docs/screenshots/case-detail-desktop_1440x900_loaded.png` | 1440×900, loaded TechBuild case overview and projected next hearing | `GET /api/v1/cases/{id}`, `GET /api/v1/cases/{id}/overview` |
| `docs/screenshots/clients-desktop_1440x900_loaded.png` | 1440×900, loaded directory including zero case count | `GET /api/v1/clients` |
| `docs/screenshots/clients-desktop_1440x900_retry-success.png` | 1440×900, transient failure followed by successful retry and real rows | First two client fetches intercepted as 503; Retry then real `GET /api/v1/clients` |
| `docs/screenshots/tasks-desktop_1440x900_loaded.png` | 1440×900, populated groups, due dates, priorities, completion and case context | `GET /api/v1/tasks`, `GET /api/v1/cases?page_size=100` |
| `docs/screenshots/tasks-mobile_390x844_action-menu.png` | 390×844, loaded task list with mobile action menu open | Same task and case list endpoints |
| `docs/screenshots/calendar-desktop_1440x900_loaded.png` | 1440×900, loaded October month; all-day labels have no time | `GET /api/v1/calendar?from=…&to=…` |
| `docs/screenshots/calendar-mobile_390x844_selected-event.png` | 390×844, date-grouped agenda with selected next-month hearing detail | `GET /api/v1/calendar?from=…&to=…`, case titles from `GET /api/v1/cases` |
| `docs/screenshots/cases-desktop_1440x900_empty.png` | 1440×900, genuine no-match search | `GET /api/v1/cases?q=<unique-no-match>` |
| `docs/screenshots/clients-desktop_1440x900_empty.png` | 1440×900, genuine no-match search | `GET /api/v1/clients?q=<unique-no-match>` |
| `docs/screenshots/cases-desktop_1440x900_failure.png` | 1440×900, API failure state | Cases requests injected as 503; auth bootstrap remains available |
| `docs/screenshots/clients-desktop_1440x900_failure.png` | 1440×900, API failure state | Client requests injected as 503; auth bootstrap remains available |
| `docs/screenshots/tasks-desktop_1440x900_failure.png` | 1440×900, API failure state | Task requests injected as 503; auth bootstrap remains available |
| `docs/screenshots/calendar-desktop_1440x900_failure.png` | 1440×900, API failure state | Calendar requests injected as 503; auth bootstrap remains available |

Failure captures model an unreachable endpoint with browser-side 503 responses; they are not captures from a stopped backend. All loaded and empty captures use the actual freshly seeded backend.

## Gates and remaining gaps

- Round 4 baseline: 25 E2E tests passed.
- Round 5 full `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm test:e2e`: **28 passed, 1 skipped** (29 total). The skipped check is cross-user authorization pending a second seeded user.
- After strengthening the agenda pagination assertion, focused `calendar mobile defaults to readable agenda view`: **1 passed**.
- `pnpm format`: passed.
- `pnpm lint`: passed with no ESLint warnings or errors (Next emits its `next lint` deprecation notice).
- `pnpm typecheck`: passed.
- `pnpm build`: passed; Next generated all 17 app routes.
- `pnpm screenshots`: passed; 9 loaded captures, 2 genuine empty states and 4 simulated failure states.

Open items: cross-user authorization remains untested until a second user is seeded. Client edit/delete/status CRUD, team assignment, and the backend-unavailable Research/Activity resources remain as documented in the historical sections below. No backend files were edited. The nine-item shell navigation was unchanged this round.

## Round 5 commits

Implementation, tests, each screenshot, and this report are committed one file per commit. No push or merge was performed. The user-provided untracked `target-crops/` directory is not included.

- Playwright config `c75bc0a`; Calendar UI `653878a`; case-list placeholder `e2337a5`; feature styles `c062665`; Clients UI `1bed1bd`; Tasks UI `17d39c3`.
- Capture harness `825bb91`; route/mobile E2E `1d2eae7`; hearing/all-day regressions `9f32c20`; API contracts `6a9eb66`.
- Loaded captures: Cases desktop `0233cf2`, Cases mobile `f79d5cd`, case detail `3a3f82c`, Clients loaded `09a5435`, Clients retry `70da8a3`, Tasks desktop `5c3b79a`, Tasks mobile action menu `107e684`, Calendar desktop `dccf0c4`, Calendar selected event mobile `5c97339`.
- Empty captures: Cases `b1f947d`, Clients `f62db58`.
- Failure captures: Cases `7a24232`, Clients `e75db51`, Tasks `5a72ab6`, Calendar `fa0f2ca`.
- This report is committed separately after the above.
