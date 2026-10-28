# Open issues

- Draft Save persistence is unresolved: in `frontend/tests/drafts-captures.spec.ts`, the edited phrase appears in the editor after reload but is absent from the subsequent real `GET /drafts/{id}` response. Do not treat draft editing as complete until the server response persists the edit.
- Full Playwright suite has not been rerun after the latest focused fixes. Last full run: 81 passed, 4 failed, 2 skipped, 3 did not run. Focused reruns passed for strategy follow-up, seeded document capture, library preview, and unavailable-drafts behavior.
- `review-tools/verify_integration.sh` has not been run in this pass.
