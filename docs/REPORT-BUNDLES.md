# Filing Bundles and Strategy Advisor — Round 2

## Delivered

- `/bundles` lists persisted bundles with API status, case, section count, and creation date; it creates bundles using the measured `{name, case_id, settings}` contract.
- `/bundles/[id]` reopens persisted bundles, reads the actual source-to-bundle page map from `GET /preview`, edits section/ranges and section order, prevents selecting a duplicate document, shows validation failures, and previews/downloads the generated PDF only when ready. Download checks `%PDF-` bytes. Scanned pages are identified as potentially image-only and not searchable.
- The strategy routes provide case selection/context and the six URL-synced tabs. Template/source-excerpt output is explicitly described as assembled without a language model; empty sections remain empty, citations show source title/page, and generated-response counts are not shown before analysis. Edits persist via PUT, with saved version feedback; task creation uses the tasks API and follow-up opens the research desk with a prefilled question.
- Workspace navigation exposes Bundles and Strategy with active state. The `/research` bridge submits the prefilled prompt through the real AI ask endpoint.

## Defects closed

| Defect | File(s) | Change | Test and assertion | Capture |
|---|---|---|---|---|
| Saved bundle inaccessible | `frontend/src/app/(workspace)/bundles/[id]/page.tsx` | Added real persisted detail route and PDF actions | `seeded bundle opens from its real API id...`: fetched the ID from `GET /bundles`, asserted persisted heading, page map, preview and `%PDF-` download | `capture not retained` |
| Setup absent from bundles landing page | `frontend/src/app/(workspace)/bundles/page.tsx` | Real list/create flow and honest empty state | `staff sees the real empty bundle state...`: asserts empty state and desktop navigation | `capture not retained` |
| No module navigation | `frontend/src/components/shell.tsx` | Added workspace module links and active state | `staff sees...`: links visible in desktop sidebar and mobile drawer; `desktop navigation marks active...`: `aria-current=page` | `capture not retained`; mobile drawer asserted in same test |
| Strategy lacked case context | `frontend/src/app/(workspace)/strategy/page.tsx`, strategy feature files | Case picker and visible case overview; generation is sent to selected case ID | `strategy shows source excerpts honestly...`: selected test case is visible and its own document is moved into that case before generate; response citations reference it | `capture not retained` |
| Mobile tabs clipped; layout setup hard to reach | `frontend/src/features/strategy/strategy.css`, bundle feature CSS | Responsive tab grid and stacked bundle controls | `strategy shows...`: activates each exact tab at 390px; `bundle and strategy routes remain settled...`: widths 1440/1024/768/390 and no overflow | `capture not retained`; `capture not retained` |
| Unanalysed strategy showed false zero counters | `frontend/src/features/strategy/StrategyPanel.tsx` | Shows “Not analysed” until a generation response exists | `strategy shows...`: asserts Not analysed before Generate | `capture not retained` |
| Template mode risked implying generated analysis | `frontend/src/features/strategy/StrategyPanel.tsx` | Explicit no-language-model label, source excerpts, real citation title/page, absent sections | `strategy shows...`: dead local model endpoint returns unavailable state and every shown excerpt has a citation page | `capture not retained` |
| No-evidence state unclear | `frontend/src/features/strategy/StrategyPanel.tsx` | Shows backend no-evidence message and no generated strategy | `case without indexed evidence...`: asserts exact no-evidence and no-strategy text | `capture not retained` |
| Notes/task/follow-up actions unproven | Strategy panel and `/research` bridge | Persist notes, create task, open prefilled research question | `strategy shows...`: reload preserves edited value, task is found in `GET /tasks`, research textarea contains prefilled query | `capture not retained`; `capture not retained`; `capture not retained` |
| Invalid range left stale unsaved values visible | `frontend/src/app/(workspace)/bundles/[id]/page.tsx` | Reloads persisted values after rejected update, retains backend error | `page-range 400 is shown...`: asserts backend 400 message and duplicate document option absent | `capture not retained`; `capture not retained` |

## Verification

Commands run from `frontend/`:

- `TANTARA_WEB_URL=http://127.0.0.1:3015 TANTARA_API_URL=http://127.0.0.1:8116/api/v1 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8116 pnpm exec playwright test tests/bundles-strategy-live.spec.ts` — **9 passed (1.5m)** against the isolated live backend; no route stubs. The 400 range rejection is the one expected browser console network error and is asserted by the capture helper.
- `pnpm lint` — exit 0, no ESLint warnings or errors (Next reports `next lint` deprecation).
- `pnpm typecheck` — exit 0 (`tsc --noEmit`).
- `pnpm build` — exit 0; Next compiled and generated all 9 static pages. An earlier build overlapped the running dev server and failed while both processes shared `.next`; after stopping the owned dev server, the clean production build passed.

The Playwright API test checks missing `name` and forbidden extra fields (422), anonymous access (401), another seeded user access (404), empty bundle mapping, full-document and page-1 ranges, and out-of-range rejection (400). UI workflow verifies the real seeded bundle ID, generated state, download signature, the chosen source pages 2–4 mapping to bundle pages 5–7, duplicate prevention, and generation. Strategy tests use a real case/document and dead configured model endpoint; the backend returned `model_unavailable` with source excerpts. The test restores AI settings, document ownership, and archives its temporary case.

## Captures

All captures are authenticated, settled, real-backend screenshots (no fixtures). Desktop is 1440×900; mobile is 390×844. Bundle endpoints refer to `/api/v1`.

| File | Viewport and state | Data endpoints exercised |
|---|---|---|
| `capture not retained` | 1440×900, staff empty list | `GET /bundles`, `GET /cases` |
| `capture not retained` | 1440×900, seeded persisted bundle and mapping | `GET /bundles/{id}`, `GET /bundles/{id}/preview`, `GET /documents`, `GET /cases` |
| `capture not retained` | 1440×900, created bundle with source pages 2–4 | `POST /bundles`, `GET /documents`, `PUT /bundles/{id}/sections`, `PUT /bundles/{id}/items`, `GET /bundles/{id}/preview` |
| `capture not retained` | 1440×900, ready generated PDF | Above plus `POST /bundles/{id}/generate`, `GET /bundles/{id}` |
| `capture not retained` | 390×844, ready state and visible download | `GET /bundles/{id}`, `GET /bundles/{id}/preview` |
| `capture not retained` | 1440×900, 400 error with persisted range restored | `PUT /bundles/{id}/items` (400), `GET /bundles/{id}`, `GET /bundles/{id}/preview` |
| `capture not retained` | 1440×900, duplicate removed from add choices | `GET /bundles/{id}`, `GET /bundles/{id}/preview`, `GET /documents` |
| `capture not retained` | 1440×900, unanalysed state | `GET /cases`, `GET /cases/{id}/strategy` |
| `capture not retained` | 1440×900, real source excerpts with dead model configured | `PATCH /settings/ai`, `POST /cases/{id}/strategy/generate`, `GET /documents` |
| `capture not retained` | 390×844, all six tabs activated, source excerpt state | `GET /cases/{id}/strategy` |
| `capture not retained` | 1440×900, persisted lawyer edit after reload | `PUT /cases/{id}/strategy`, `GET /cases/{id}/strategy` |
| `capture not retained` | 1440×900, task-created result | `POST /tasks`, `GET /tasks` |
| `capture not retained` | 1440×900, follow-up prompt prefilled in research desk | Navigation from strategy; research submission uses `POST /ai/ask` when submitted |
| `capture not retained` | 1440×900, backend no-indexed-evidence state | `POST /cases/{id}/strategy/generate`, `GET /cases/{id}/strategy` |

Paths are `docs/screenshots/`.

## What remains unproven / backend limits

- This checked-out backend returns 405 for `GET /bundles/{id}/items`; the UI uses the real `GET /bundles/{id}/preview` response for the persisted items and page mapping. No undocumented items endpoint is assumed.
- The backend reports page mappings and the generate response's page total; tests assert the selected source range maps to bundle pages 5–7 and assert the downloaded bytes begin `%PDF-`. The test does **not** parse the merged PDF to independently count its internal page objects or compare every index-printed range against PDF text. Thus PDF-internal page-count/index consistency remains unproven by this round's automated test.
- Backend strategy generation does not call the language model in template mode; template responses are labeled as source excerpts. A dead configured endpoint was tested and produced `model_unavailable`; a `model_generated` result was observed in a separate live probe but is not represented by a screenshot or automated assertion here. No claim of outcome prediction is made.
- Scan/OCR extraction quality and manual review of rotated or mixed-size documents were not independently validated. The UI warns that scanned pages may be image-only and not searchable.
- The development server was stopped before the clean production build. Backend test data is isolated under `/tmp/l7b-data`; no shared integration backend was used.
