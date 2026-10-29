# Test execution and skip policy

## Playwright

Capture tooling guard tests run from `frontend/` with `pnpm test:tools` (`node --test "scripts/**/*.test.mjs"`).

Run the end-to-end suite from `frontend/` with `pnpm test:e2e`. The Playwright configuration provisions a fresh seeded data directory and starts one backend and one frontend for the run. API-backed specs are unconditional: a missing or unhealthy API is a test setup failure, not a reason to skip. The shared `tests/api-readiness.ts` check reports the configured health URL and the backend web-server log path (`TANTARA_BACKEND_LOG_FILE`).

The suite is configured with one worker because its tests share the run's SQLite database. Tests that write data clean up the records they create when the API contract supports deletion; soft-deleted case records are asserted as archived where appropriate.

There are no `test.skip(...)` calls in `frontend/tests/`. When a test is not runnable because of a required service or fixture, the setup must fail with the missing dependency rather than silently lower coverage.

## Backend

Run the API and integration tests with:

```bash
cd backend
.venv/bin/python -m pytest -q --cov=app
```

Contract tests cover error envelopes, ownership, collection scope, document storage, draft exports, and paperbook output. Keep assertions strict when a contract has a defined status or response shape.
