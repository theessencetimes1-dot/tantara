# M3 final validation report

Validation was run on `feat/tantara-workspace` at implementation HEAD `3f58e91` before this report and the two refreshed screenshots were committed. No `main` or `sensitive/` paths were accessed.

## Frontend gates

Commands ran from `frontend/`.

```text
$ pnpm exec tsc --noEmit
[exit 0; no stdout]
```

```text
$ pnpm lint
$ next lint && pnpm format:check && ! grep -R -F 'page.route(' tests
`next lint` is deprecated and will be removed in Next.js 16.
For new projects, use create-next-app to choose your preferred linter.
For existing projects, migrate to the ESLint CLI:
npx @next/codemod@canary next-lint-to-eslint-cli .

✔ No ESLint warnings or errors
$ prettier --check "src/**/*.{ts,tsx,css}" tests
Checking formatting...
All matched files use Prettier code style!
```

```text
$ pnpm build
$ next build
   ▲ Next.js 15.5.28

   Creating an optimized production build ...
 ✓ Compiled successfully in 23.2s
   Linting and checking validity of types ...
   Collecting page data ...
   Generating static pages (0/23) ...
   Generating static pages (11/23)
   Generating static pages (17/23)
 ✓ Generating static pages (23/23)
   Finalizing page optimization ...
   Collecting build traces ...
[exit 0; route table and static/dynamic route summary follow in /tmp/tantara-m3-build.log]
```

## Backend suite and migration

```text
$ /home/kahitoz/projects/tantara-wt/be/backend/.venv/bin/python -m pytest -q --cov=app
TOTAL                                3226    226    93%
114 passed in 283.63s (0:04:43)
```

Alembic reported one head:

```text
$ /home/kahitoz/projects/tantara-wt/be/backend/.venv/bin/python -m alembic heads
0010_collections (head)
```

A fresh disposable SQLite data directory `/tmp/tantara-m3-alembic.IW7t4P` upgraded through `0010_knowledge_collections -> 0010_collections`; `alembic current` reported `0010_collections (head)`.

## Full Playwright suite

The full suite used one fresh isolated data directory and the required single stack at API `127.0.0.1:8010` and web `127.0.0.1:3010`:

```text
$ TANTARA_TEST_DATA_DIR=/tmp/tantara-m3-playwright-final-3 \
  TANTARA_PYTHON=/home/kahitoz/projects/tantara-wt/be/backend/.venv/bin/python \
  TANTARA_API_ORIGIN=http://127.0.0.1:8010 \
  TANTARA_WEB_URL=http://127.0.0.1:3010 \
  pnpm exec playwright test --reporter=line
  108 passed (12.5m)
```

Full runner log: `/tmp/tantara-m3-playwright-final-3.log`.

Separate fresh-seed authenticated screenshot checks passed: calendar and tasks `2 passed (1.8m)`; dashboard case table `1 passed (43.0s)`. The test asserts the authenticated navigation, stored token, and viewport width before capture. Only the dashboard and calendar root screenshots were retained from these runs; task and all incidental suite screenshots were restored.

## Refreshed evidence

- `docs/screenshots/dashboard-1440x900.png` — fresh seeded dashboard, 1440×900.
- `docs/screenshots/calendar-1440x900.png` — fresh seeded calendar, 1440×900.

Both were captured from the current repository frontend with an authenticated session after the capture test's readiness assertions. They contain no test-created all-day proof event or wall-time task.

## Deferred items

- **R6, historical hearing distinction:** case API exposes an upcoming-only `next_hearing_at` and no past-hearing history indicator. The UI cannot truthfully distinguish “no hearings” from “only past hearings” using the current contract; this remains deferred pending an additive history field.
- **R27/R32, legacy screenshot corpus cleanup:** the bounded cleanup removed the five approved stale root desktop captures and nine obsolete failure captures. The duplicate `frontend/docs/screenshots/` corpus and its five remaining 1440×1000 captures are deferred to avoid wholesale image churn. Root README-linked images were audited separately; this report does not claim the duplicate corpus is removed.

## Logs and limitations

The raw full-suite, backend, TypeScript, lint, build, and migration command outputs were retained during this run under `/tmp/tantara-m3-*.log` where applicable. The current report records their exact final summaries and command outcomes. The external `verify_integration.sh` was not rerun as part of this M3 closeout command set; no new claim is made about that script here.
