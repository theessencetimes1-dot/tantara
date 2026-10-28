# L6e — AI Drafts + Smart Autofill

## Current result

Presentation changes and real HTTP contract tests are verified to the extent listed below; the changed files are being committed individually. The UI capture run is **blocked**: port 3014 is occupied by a Next server whose working directory is `/home/kahitoz/projects/tantara-wt/fe4/frontend`. I did not stop or reuse it, and the required captures were not produced. The capture test writes to `frontend/docs/screenshots/` and contains no `page.route()` calls; its assertions need a run against this worktree before this round can be called visually verified.

Step 0 pushed the previously unpushed branch tip `52526297416fbc3f04c60e4056c7fb1ea2466ae3` to `origin/luna/frontend-drafts` before publishing these L6e changes.

## Findings and changes

| Defect | File and change | Test and assertion |
| --- | --- | --- |
| Model deliberation shown as a pleading | `frontend/src/app/(workspace)/drafts/page.tsx`: validate for recognizable pleading sections (`Parties`, `Facts`, `Claim`, `Relief Sought`, etc.), sufficient body text, and known deliberation patterns. Invalid output shows **Generated text needs editing — structure not recognised**, Retry, and a closed raw-output disclosure. The model response is only whitespace-normalized. | `drafts-captures.spec.ts` / `captures live seeded drafts and autofill states at desktop and mobile sizes`: checks no editor is mounted for rejected text, raw output is hidden until disclosure, and any rendered editor text lacks “We need to draft a”. **Not run** because 3014 belongs to `fe4`. |
| Model call evidence not visible | Same file shows API model id and `generation_kind` in the workspace header. | Same capture test checks both against the real generation response. **Not run** because 3014 belongs to `fe4`. |
| Version numbers invented from row order | Same file uses API `version_number`, otherwise `Snapshot · <formatted timestamp>`; restore confirmation and status say “Snapshot restored” when the number is absent. The history is in a Draft/Review/Sources/History tab. | Same capture test checks the label matches `Version <number>` or `Snapshot · …`, Current marker and separated timestamp; after Restore it checks the editor content. It checks every version-row descendant's horizontal bounds at 1440 and 390. **Not run** because 3014 belongs to `fe4`. |
| Editor save bypassed version API | Same file now saves through `POST /drafts/{rid}/versions`, rejects whitespace-only content locally, and refreshes history. | Same capture test saves, reloads, and asserts at least two snapshots and retained unique text. **Not run** because 3014 belongs to `fe4`; the real API suite covers snapshot and restore behavior. |
| Citation `#` destinations | Same file links known document/page pairs directly and renders “Source page unavailable” without a link when the source is unknown. | Same capture test checks the destination URL and visible `#page-N` viewer content when a generated citation link exists. **Not run** because 3014 belongs to `fe4`. |
| Autofill decision was ambiguous | `frontend/src/app/(workspace)/autofill/page.tsx` retains Accepted/Rejected decisions in the row's accessible name after application and reports the accepted count on Apply. Unknown source pages have no link; long values have a read-full-value disclosure. | Same capture test checks the row accessible name includes Accepted, Apply says `(1 accepted)`, and the applied row keeps that state. **Not run** because 3014 belongs to `fe4`. |
| Autofill review density | Same file and `frontend/src/features/autofill/styles.css` render compact field rows, source/provenance information, and wrapped long values. Confidence remains `—` when unmeasured. | Capture test checks per-field provenance and that Apply is in the first mobile viewport. **Not run** because 3014 belongs to `fe4`. |
| Draft list content hierarchy | `frontend/src/app/(workspace)/drafts/page.tsx` places creation before recent drafts, collapses source inventory, bounds recent rows, and separates status, title, timestamp and Open. A feature-owned AI Drafts nav destination is added to the existing shell nav through a portal; the shared shell source was not edited. | Capture test sets up 21 real drafts, checks the primary action fits the first mobile viewport, row metadata is separate, and the mobile drawer destination fits and closes on selection. **Not run** because 3014 belongs to `fe4`. |
| Date-year hallucination guard | Existing `autofill-date-guard.spec.ts` remains unchanged. | `a statute year is never written into a date field` verifies `1996` is rejected as a date and not applied. **Not run in L6e** because its page-based fixture needs the correct frontend server. |

The model prompt is the root cause of the deliberation text. The live API probe returned `generation_kind: "model_generated"` and `model.model: "MiniCPM5-2B"`, but the content begins with process narration (“We are asked…”, “We must…”, “We have a bunch of chunks…”) and competing drafting analysis. The UI now withholds that response rather than rewriting it. A backend prompt change is needed to produce usable pleading text.

## API ground truth and endpoint tests

Fetched `http://127.0.0.1:8115/openapi.json` from `/home/kahitoz/projects/tantara-wt/be/backend`. The live OpenAPI included:

```text
GET  /api/v1/draft-templates
GET  /api/v1/drafts
POST /api/v1/drafts
GET  /api/v1/drafts/{rid}
POST /api/v1/drafts/generate
GET  /api/v1/drafts/{rid}/versions
POST /api/v1/drafts/{rid}/versions
POST /api/v1/drafts/{rid}/versions/{vid}/restore
POST /api/v1/drafts/{rid}/regenerate-section
GET  /api/v1/drafts/{rid}/export
GET  /api/v1/cases/{cid}/autofill
POST /api/v1/cases/{cid}/autofill/preview
POST /api/v1/cases/{cid}/autofill/apply
GET  /api/v1/settings/ai
PATCH /api/v1/settings/ai
```

| Endpoint | Test coverage |
| --- | --- |
| `GET /draft-templates`, `GET /drafts`, `POST /drafts`, `GET /drafts/{rid}` | `drafts-api.spec.ts`: templates/list, create, get, ownership. Capture test adds real list and draft reload assertions; blocked at UI server startup. |
| `POST /drafts/generate` | `drafts-api.spec.ts`: missing required data validation envelope, anonymous 401 and empty-evidence generation. Capture test checks real seeded case title/parties plus returned model id and generation kind; blocked at UI server startup. |
| `GET /drafts/{rid}/versions`, `POST /drafts/{rid}/versions`, `POST /drafts/{rid}/versions/{vid}/restore` | `drafts-api.spec.ts`: saved history, optional-content snapshot, restore success, auth and cross-user access. Capture test covers UI reload/restore; blocked at UI server startup. |
| `POST /drafts/{rid}/regenerate-section` | `drafts-api.spec.ts`: valid section response preserves other content; invalid payload envelope and authorization. |
| `GET /drafts/{rid}/export` | `drafts-api.spec.ts`: real DOCX/PDF content type, non-trivial bytes, `PK\x03\x04` and `%PDF` magic, review marker text. Capture test additionally checks a unique saved phrase in DOCX XML/PDF text; blocked at UI server startup. |
| `GET /cases/{cid}/autofill`, `POST /cases/{cid}/autofill/preview`, `POST /cases/{cid}/autofill/apply` | `drafts-api.spec.ts`: success, validation envelope, anonymous 401 and cross-user denial. UI accept/apply persistence checks are coded in capture test; blocked at UI server startup. |
| `POST /cases/{cid}/autofill` | Not in live OpenAPI; `drafts-api.spec.ts` asserts absence and the actual request returns 405. The backend exposes case-scoped GET/preview/apply instead. |
| `GET /settings/ai`, `PATCH /settings/ai` | `drafts-captures.spec.ts` changes the authenticated setting to a closed port, checks unavailable state, retries a real generation, and restores the setting. **Not run** because 3014 belongs to `fe4`. |

## Capture inventory

All listed captures are intended to be real-backend captures (`fixture-backed: no`); no image was generated in this round. The test uses `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8115`, requires the seeded case reference from `GET /api/v1/cases`, asserts the saved auth token, sets exact viewport sizes, checks skeletons, and checks mobile horizontal overflow.

| Expected filename | Viewport | State and data endpoint | Result |
| --- | --- | --- | --- |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | 21-row seeded list, separated metadata, visible Start a draft; `GET /api/v1/drafts`, `GET /api/v1/cases` | Not captured: 3014 occupied by `fe4`. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Case-sourced review draft with editable sections and review marker; `POST /api/v1/drafts`, `GET /api/v1/drafts` | Not captured: 3014 occupied by `fe4`. This is a case-sourced editor surface, not proof that the model generated usable pleading text. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Live generated model response withheld behind structure warning; `POST /api/v1/drafts/generate` | Not captured: 3014 occupied by `fe4`. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Saved unique edit, restore confirmation, current marker and history tab; `POST /api/v1/drafts/{rid}/versions`, `GET /api/v1/drafts/{rid}/versions`, `POST /api/v1/drafts/{rid}/versions/{vid}/restore` | Not captured: 3014 occupied by `fe4`. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Per-field provenance, source and accepted review state; `GET /api/v1/cases/{cid}/autofill`, `POST /api/v1/cases/{cid}/autofill/preview` | Not captured: 3014 occupied by `fe4`. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Accepted sourced value and provenance persisted in the draft; `POST /api/v1/cases/{cid}/autofill/apply`, `POST /api/v1/drafts/{rid}/versions`, `GET /api/v1/drafts/{rid}` | Not captured: 3014 occupied by `fe4`. |
| `capture not retained`, `capture not retained` | 1440×900, 390×844 | Dead-port unavailable state and real retry attempt; `PATCH /api/v1/settings/ai`, `POST /api/v1/drafts/generate` | Not captured: 3014 occupied by `fe4`. |

## Commands and results

- `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8115 TANTARA_WEB_URL=http://127.0.0.1:3014 pnpm exec playwright test tests/drafts-api.spec.ts --reporter=line` — **5 passed (5.7s)** against the private lane backend.
- `pnpm lint` — **passed**, `✔ No ESLint warnings or errors`.
- `pnpm exec prettier --check 'src/app/(workspace)/drafts/page.tsx' 'src/app/(workspace)/autofill/page.tsx' src/features/drafts/styles.css src/features/autofill/styles.css tests/drafts-captures.spec.ts tests/drafts-api.spec.ts` — **passed**, “All matched files use Prettier code style!”.
- `pnpm exec tsc --noEmit` — **passed**, exit 0.
- `pnpm build` — **passed**, production build and routes generated.
- `pnpm format:check` — unavailable: this worktree's `frontend/package.json` has no `format:check` script. The equivalent targeted Prettier check above passed.
- Capture/browser suite — **not run against this worktree**. `ss -lptn 'sport = :3014'` identified PID 1544970 from `fe4/frontend`; no screenshot was written. No pytest suite applies to this frontend lane.

## Remaining proof gaps

- No L6e screenshots or UI Playwright pass counts exist yet; the assigned 3014 server must become free before the capture suite can run. No file under `frontend/docs/screenshots/` should be treated as evidence from this round until then.
- The local model was reachable and identified itself as `MiniCPM5-2B`, but the generated content is process narration. The UI guard proves withholding only when the capture suite can run; usable model-authored pleading text remains a backend prompt gap.
- The current live API has no direct `POST /cases/{cid}/autofill` operation. AI suggestions are not proven; unmeasured confidence remains `—`.
- Real visible citation navigation, mobile drawer behavior, autofill acceptance presentation, and model-unavailable retry still need the UI run on 3014.
