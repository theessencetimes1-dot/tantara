# Cases / Clients / Tasks / Calendar delivery report

## Built

- `/cases`, `/cases/active`, `/cases/pending`, and `/cases/archived`: API-backed case search, server pagination/sorting, status filters with counts fetched from the API, loading/error/empty states, demo-data labels, create navigation, and row actions with case-named confirmation.
- `/cases/new` and `/cases/[id]/edit`: validated case forms using React Hook Form and Zod, institution/client selects, key case fields and dates, server error toasts, and an unsaved-change guard.
- `/cases/[id]`: URL-selected workspace tabs, overview facts and claim amount formatting, participant/strategy views, and quick links. Strategy generation and saving call the API.
- `/clients` and `/clients/[id]`: API-backed directory/search, client creation, details, and linked cases.
- `/tasks`: API-backed task grouping and create flow, with optimistic completion and rollback.
- `/calendar`: API-backed month and agenda views with month navigation and an Asia/Calcutta label.
- Dashboard Matters card: compact five-row case table with API counts and links to case workflows.

## Files

- Routes: `frontend/src/app/(workspace)/{cases,clients,tasks,calendar}/**`
- Feature code: `frontend/src/features/{cases,clients,tasks,calendar}/**`
- Dashboard insertion/card: `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/features/dashboard/matters/index.tsx`
- E2E and screenshot helpers: `frontend/tests/cases-real-api.spec.ts`, `frontend/tests/smoke.spec.ts`, `frontend/tests/capture-owned-routes.mjs`

## Verification

- `pnpm install --frozen-lockfile`: packages were linked, but pnpm exited 1 because its build-script policy rejected `unrs-resolver@1.12.2` (`ERR_PNPM_IGNORED_BUILDS`).
- `pnpm lint`: passed, no warnings or errors.
- `pnpm typecheck`: passed.
- `pnpm build`: passed; all new routes appeared in the production route table.
- `pnpm test:e2e`: passed, 10 tests. The real API workflow created a client, case, participant, hearing, and task, exercised table search/sort, reloaded, and verified persisted case data. Route smoke covered 11 owned routes at 1440, 1024, 768, and 390 px with no console errors or horizontal overflow.
- Screenshots were generated from the local API using `node tests/capture-owned-routes.mjs`.

## Screenshots

- `docs/screenshots/cases-desktop.png`
- `docs/screenshots/cases-mobile.png`
- `docs/screenshots/case-detail-desktop.png`
- `docs/screenshots/clients-desktop.png`
- `docs/screenshots/tasks-desktop.png`
- `docs/screenshots/calendar-desktop.png`
- `docs/screenshots/calendar-mobile.png`
- `docs/screenshots/dashboard-desktop.png`

## Gaps

- The case list currently uses a hand-rendered table rather than TanStack Table.
- The running API does not expose the requested notes, activity-log, case-specific GET hearings/tasks, or GET participants routes. Timeline event creation, party management controls, and complete read-only Documents/Research/Drafts lists are not implemented.
- Strategy is editable and calls generate/save, but source citations are not yet classified and displayed per argument as supported evidence versus hypothesis.
- Client editing/deletion and the full client status/notes workflow are incomplete.
- Task creation currently exposes title and due date; case, priority, status, and notes controls are incomplete.
- Calendar has month and agenda views; Week currently shares the month grid, and the add-hearing dialog and explicit timezone conversion are incomplete.
- The case form omits assigned team selection because no corresponding field is present in the running API schema. Dispute category is free text rather than a metadata select.
- `devIndicators` remains enabled in `next.config.ts`; that shared configuration file is outside this lane's allowed edit paths. Requested screenshots were captured from the production build, so they do not include the development indicator.
- Per-file commits are listed below.

## Per-file commits

- `4af7659` — cases route
- `d706902` — active cases route
- `8a3545b` — pending cases route
- `fef2a01` — archived cases route
- `d2c92cb` — new case route
- `d399ae9` — case edit route
- `2099898` — case detail workspace
- `71f79cb` — clients directory route
- `bdf939d` — client detail route
- `1c58851` — tasks route
- `8d9d8f8` — calendar route
- `88b8449` — case API wrappers
- `0d494e8` — cases styles
- `1a50e4f` — cases table
- `adc14df` — case forms
- `9902d51` — strategy editor
- `d6c7707` — client API wrappers
- `af17c0a` — client directory
- `24b6d1f` — tasks workspace
- `c599782` — calendar workspace
- `2c79e22` — dashboard Matters card
- `40e3a7f` — dashboard insertion
- `d6d3177` — Playwright server configuration
- `dfd6506` — API smoke fixtures
- `dc38a7d` — route smoke coverage
- `c1608aa` — real API workflow test
- `620dbac`, `1fabb28` — screenshot helper and CORS proxy
- `1cde17e` — cases desktop screenshot
- `e5731db` — cases mobile screenshot
- `46720ee` — case detail screenshot
- `1a149c4` — clients screenshot
- `e807449` — tasks screenshot
- `fb92ebb` — calendar desktop screenshot
- `55593ac` — calendar mobile screenshot
- `d7bfcaa` — dashboard screenshot
- `f152d7a` — this report
