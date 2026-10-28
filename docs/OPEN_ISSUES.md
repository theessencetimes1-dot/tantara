# Open issues and verification notes

This ledger records only current product gaps or evidence gaps. The M4 fixes for duplicate module navigation, model-backed Research Desk synthesis, 405 error vocabulary, API readiness skips, mobile client visibility, nested client navigation, Strategy claim tolerance, timestamp display, and Autofill date validation have been implemented and covered by current tests. The full browser suite currently reports 109 passed and 0 skipped.

## Open findings

| Finding | Evidence | Follow-up |
|---|---|---|
| Screenshot evidence is split across duplicate tracked corpora. | `git ls-files docs/screenshots | wc -l` reports 109 images while `git ls-files frontend/docs/screenshots | wc -l` reports 96; `captures-fe7/` is also tracked. Several duplicate-era captures do not reflect the current 14-link rail, so they are not current product evidence. | Curate a single root `docs/screenshots/` corpus, migrate only current authenticated captures, update references, and remove obsolete duplicate copies in a dedicated evidence-cleanup pass. |
| The timestamp suite does not compare one identical instant across Community and Dashboard. | `frontend/src/lib/datetime.ts` formats both modules with `WORKSPACE_TIME_ZONE`, and the Community browser test checks the workspace label, but no test feeds the same fixed instant to both rendered surfaces. | Add one deterministic browser assertion that renders the same offset-bearing instant in both components and compares the displayed wall-clock text. |
| Cases cannot distinguish “no hearings” from “past hearings only.” | `frontend/src/features/cases/components/case-list.tsx` renders a dash when `next_hearing_at` is absent; the API intentionally returns upcoming hearings only and does not expose whether past hearings exist. | Keep current upcoming-only semantics. Revisit the wording if the API later supplies a past-hearing indicator; do not infer one in the UI. |

## Tooling and validation notes

- The external style-contract helper previously reported `auth_present: false` and no login request. Its unauthenticated style output is not evidence about authenticated routes.
- A former verifier strategy-write probe used the wrong HTTP method and returned 405; authorization is instead covered by `frontend/tests/api-domain-contracts.spec.ts`.
- The previous authorization-test skip is removed. `frontend/tests/api-domain-contracts.spec.ts` now exercises a second seeded identity and exact ownership behavior.
- The calendar hook dependency warning was corrected; `pnpm lint` reports no ESLint warnings or errors.

## Recently verified closed findings

- Documents and Search no longer render `WorkspaceModuleNav`; `rg -n 'documents-module-nav|WorkspaceModuleNav' frontend/src` returns no matches. The shell rail owns current-page navigation.
- Research Desk returns numbered model synthesis only when each marker resolves to retrieved citations; invalid synthesis falls back to cited excerpts and unavailable-model responses remain honest.
- 405 responses use `method_not_allowed`; error-envelope tests cover 401, 404, 405, 409, and 422.
- Playwright API availability checks fail loudly rather than silently skipping. The suite ran against one seeded backend and frontend with 109 passed and no skips.
- Client directory mobile cards match the desktop API row count; nested client profiles mark the Clients rail entry.
- Strategy reliability probe: 10/10 model-backed generations; some runs omit invalid individual claims and disclose those omissions.
- Autofill date application parses valid ISO dates and returns a validation envelope for malformed dates.
