# Open issues and validation limits

- The external style-contract helper does not establish an authenticated session. Its latest transcript says:

  ```text
  form_without_method: null
  auth_present: false | login_call: no-login-request-seen | url: http://127.0.0.1:3034/
  INVALID: no authenticated session — unauthenticated route diagnostics are not UI findings and must not be reported as defects.
  ```

  The helper's following no-heading/font-none output is invalid evidence. Authenticated route captures and Playwright assertions passed separately.

- The verifier's `researcher strategy write -> 403` probe returned `405`. That request does not prove authorization behavior for the intended route. The full API/Playwright suite passed its covered authorization cases, but this particular script check remains unproven.

- The full Playwright run has one intentional existing skip: cross-user client/task/calendar reads require a second seeded identity. Exact result: `1 skipped, 102 passed (9.7m)`; exit 0.

- `pnpm lint` and `pnpm build` pass with the existing React hook dependency warning at `frontend/src/features/calendar/index.tsx:137` for `cursorParts.month` and `.year`.

- The current exact `verify_integration.sh` run passes with exit 0. Its standalone `Terminated` line is emitted while stopping the background uvicorn child in relocation cleanup; the transcript then continues through frontend gates and Playwright. The fixture count label prints `<no value>` before a separate `count 0`; this is a display-only script defect. An earlier exact invocation, before `res()` gained a default, ended with `/home/kahitoz/projects/tantara-run/review-tools/verify_integration.sh: line 19: $2: unbound variable` (exit 1).

- A supplemental temporary verifier copy was first run with its Playwright API origin set to port 8193. `drafts-captures.spec.ts` correctly rejected that topology (`Expected: "8010" Received: "8193"`). The wrapper only retained the final two lines and returned 0 despite that failed test. This attempt is not acceptance evidence; the later exact script run uses the required 8010/3010 Playwright topology and passed.
