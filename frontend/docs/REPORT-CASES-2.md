# Cases / Clients / Tasks / Calendar — Sol-3 follow-up

## Routes and components

- Cases: `/cases`, `/cases/active`, `/cases/pending`, `/cases/archived`, `/cases/new`, `/cases/[id]`, and `/cases/[id]/edit`.
- Clients: `/clients` and `/clients/[id]`.
- Tasks: `/tasks`.
- Calendar: `/calendar`.
- Dashboard: compact Matters card remains below the existing metric cards; its five-row table links to the full case list.

All captured records came from the seeded API on `127.0.0.1:8112` using a temporary SQLite database and are visibly marked as sample workspace data. The capture helper no longer enables preview when it has a real token.

## Sol-3 findings: fix, files, evidence

| # | Finding | Fix | Files | Test/evidence |
|---|---|---|---|---|
| 1 | Undated tasks disappeared; task groups overlapped and used browser-local dates. | Added exclusive `Overdue / Today / This week / Later / No due date / Done` classification in `Asia/Kolkata`. | `src/features/tasks/grouping.ts`, `src/features/tasks/index.tsx` | `tasks partition into exclusive workspace-timezone groups including undated open work` uses fixed dates. |
| 2 | Missing client status was shown as Active. | Missing values display `—` with a Status unavailable title; existing status is preserved. | `src/features/clients/status.ts`, `src/features/clients/client-directory.tsx` | `missing client status remains unavailable instead of being inferred`. |
| 3 | Unknown case statuses inherited green styling and token colors differed from the reference. | Known active/pending/closed statuses use the requested tokens; all other values use neutral styling. Labels are title-cased. | `src/features/cases/status.ts`, `src/features/cases/styles.css`, `src/features/cases/components/case-list.tsx` | `case status classes use semantic colors only for known statuses`; loaded cases screenshot. |
| 4 | Case detail rendered raw JSON or fetched the case again for unrelated tabs. | Overview uses case facts and overview participants/counts. Timeline, hearings, and tasks use their resources. Notes, activity, documents, research, and drafts show explicit unavailable states when the backend has no listing endpoint. | `src/app/(workspace)/cases/[id]/page.tsx`, `src/features/cases/api.ts` | Real case detail capture; route smoke at four widths. The configured API has no notes or audit listing route. |
| 5 | “Add hearing” and “Add task” navigated without adding anything. | Relabelled as “Open calendar for this case” and “Open tasks for this case”; destinations retain `case_id` in the URL. | `src/app/(workspace)/cases/[id]/page.tsx` | Case detail capture. These actions remain navigation links, not creation dialogs. |
| 6 | Unreadable case IDs produced a blank card. | Added a retryable not-found/offline state, distinguishing HTTP 404 from other request failures. | `src/app/(workspace)/cases/[id]/page.tsx` | `case detail reports an unreadable id with a retryable not-found state`. |
| 7 | Week rendered Month; month `to` excluded the last day; Agenda lacked an empty message/retry. | Week renders seven distinct dates; month uses the exclusive next-month boundary at `+05:30`; calendar cells, today marker, local event times, dated Agenda groups, empty text, and Retry are implemented. | `src/features/calendar/index.tsx`, `src/features/cases/styles.css` | `calendar week view renders seven distinct dates`; loaded, empty, and failure captures. |
| 8 | Full Cases page linked “View all cases” to itself. | Link appears only in compact mode. Full Cases shows a real range and Previous/Next pagination. | `src/features/cases/components/case-list.tsx` | Full Cases and dashboard Matters captures. |
| 9 | Sort had no direction; status selection did not restore from URL. | Sorting toggles ascending/descending and sets `aria-sort` on the header cell. Status is restored from `?status=closed`; API receives the matching `-field` server sort syntax. | `src/features/cases/components/case-list.tsx` | `closed status restores from URL and table sorting toggles direction accessibly`. |
| 10 | Sort controls suppressed focus outline; controls lacked selected/expanded/accessibility labels. | Removed `all: unset`; status/view controls expose pressed/current state, row menus expose expanded state, and calendar navigation is labelled. | `src/features/cases/components/case-list.tsx`, `src/features/calendar/index.tsx` | Sorting regression test and four-width smoke; keyboard focus-trap testing remains open. |
| 11 | Read-only preview banner was contradicted by mutation handlers. | Create/edit case, case archive/delete, client creation, task creation, and task completion check preview at their mutation boundary; controls are disabled with a reason. | `src/features/cases/components/case-form.tsx`, `src/features/cases/components/case-list.tsx`, `src/features/clients/client-directory.tsx`, `src/features/tasks/index.tsx` | `preview case form cannot submit a mutation`. Preview UI smoke also passed. |
| 12 | Task/client in-flow dialogs were not accessible modal dialogs. | Replaced them with Radix Dialog, including focus management, Escape handling, focus restoration, labelled fields, and modal overlays. | `src/features/tasks/index.tsx`, `src/features/clients/client-directory.tsx`, `src/features/cases/styles.css` | Route smoke passed; dedicated focus-trap/Escape assertions remain open. |

### Presentation and screenshot capture

- The table keeps headers visible while loading, uses 13px/18px type, compact row spacing, normal-weight title links, and accessible horizontal scrolling on mobile. Status pills use 12px/16px text, 4px × 8px padding, and 6px radius.
- Calendar month and week cells have the required 100px desktop minimum, 8px padding, 1px `#E7EAF0` rules, and a labelled indigo today ring. On narrow screens, toolbar controls wrap and table scrolling stays inside the labelled table region.
- `tests/capture-owned-routes.mjs` waits for resource settlement, asserts that no screenshot contains a skeleton, and rejects unavailable case counts on loaded case surfaces. Empty captures use real no-match searches or an event-free month from the real API. Failure captures intercept resource requests only after real authentication.
- Offline Playwright fixtures now mark records `is_demo: true` and apply case status/search filters. No fixture-backed screenshots were produced.

## Screenshots

- `docs/screenshots/cases-desktop.png` — loaded real seeded case table (12 records, live counts).
- `docs/screenshots/cases-mobile.png` — loaded real case table at 390px with internal table scrolling.
- `docs/screenshots/cases-empty.png` — real API search with no matching matters.
- `docs/screenshots/cases-failure.png` — case API failure and Retry control.
- `docs/screenshots/case-detail-desktop.png` — loaded seeded case overview, INR claim amount, parties, and case context actions.
- `docs/screenshots/case-detail-failure.png` — backend failure on a real case ID with retry treatment.
- `docs/screenshots/clients-desktop.png` — loaded real seeded client directory.
- `docs/screenshots/clients-empty.png` — real API search with no matching clients.
- `docs/screenshots/clients-failure.png` — client API failure and Retry control.
- `docs/screenshots/tasks-desktop.png` — loaded real seeded tasks grouped by due state.
- `docs/screenshots/tasks-failure.png` — task API failure and Retry control.
- `docs/screenshots/calendar-desktop.png` — loaded real October 2026 month events.
- `docs/screenshots/calendar-mobile.png` — loaded calendar at 390px.
- `docs/screenshots/calendar-empty.png` — real event-free December 2026 Agenda period.
- `docs/screenshots/calendar-failure.png` — calendar API failure and Retry control.
- `docs/screenshots/dashboard-desktop.png` — regenerated dashboard with the Matters card and existing metrics.

## Quality gates

Run against the seeded isolated backend and frontend origin `http://localhost:3011`:

- `pnpm install --frozen-lockfile` — passed; workspace `allowBuilds` now approves `unrs-resolver` and `sharp`.
- `pnpm format` — passed.
- `pnpm lint` — passed with no ESLint warnings or errors.
- `pnpm typecheck` — passed.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm build` — passed; all owned routes compiled.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm test:e2e` — 17 passed. Includes the real client→case→party→hearing→task persistence workflow, route smoke at 1440/1024/768/390, fixed-date task groups, status truthfulness, preview mutation guard, case not-found, URL filter restore/sort direction, and seven-day week.
- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8112 pnpm screenshots` — passed; generated 8 loaded real-data captures, 3 genuine empty states, and 5 API failure states.

## Commits

Implementation and screenshot work is recorded in 49 single-file commits on `luna/frontend-cases`, from `c26ab56` through `afe1b51`, followed by this report-only commit. No push or merge was performed.

## Remaining gaps

- The shared shell is outside this lane. Its navigation still omits Cases/Clients/Tasks and Calendar, and its profile identity/avatar remain hard-coded; no shell changes were made.
- Client directory supports creation and linked-case/notes viewing, but not full edit/delete/status CRUD. Parties are displayed but cannot yet be added/edited/removed from case detail.
- Task creation does not yet expose case link, priority, status, or notes fields; task edit is not implemented. Case form still lacks assigned team member selection. Hearing creation and timeline event/notes editors are not implemented.
- This backend has no case-scoped notes, audit, document, research, or draft listing endpoints. Those tabs explicitly explain the gap instead of fabricating data or presenting the case object as another resource.
- Dedicated keyboard assertions for Radix focus trapping, Escape close, and focus restoration are not included; the components use Radix Dialog’s built-in accessible behavior.
