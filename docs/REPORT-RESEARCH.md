# Research Desk round 3 report

## Changes

- Citation references render as human links such as **Page 3 [1]**. Chunk IDs stay in `data-chunk-id`; answer prose is cleaned of raw UUID references. Citation links carry the document, page, and chunk query parameters.
- Source hits are grouped by document, page links are shown once per page, and identical excerpts appear once per document. The API document title is rendered after whitespace/escaped-newline cleanup. Relevance is shown to two decimals with rank and “relative to this query” framing. Human status labels are exposed alongside machine `data-status` values.
- The answer uses one answer-level source set rather than attaching every citation to every sentence. Case-record fields are labelled “from the case record”; conflicts can show the case value and the cited excerpt/page; `insufficient_evidence` suppresses answer citations and sources. These additive L9j paths are implemented conditionally but were not returned by the current backend (see gaps).
- Opening a history or saved answer restores the full session and hydrates document titles and citations. The active session ID persists through reload. Scope filtering associates sessions with jurisdictions through their linked live document records because this backend’s session records do not carry jurisdiction.
- The mobile shell exposes all nine destinations behind the off-canvas navigation button. Research content and the header controls remain inside the 390px viewport. Screenshot capture waits for the sidebar transition to finish before taking mobile evidence.
- Unavailable-model copy contains no endpoint, host, port, or exception. It offers Retry and shows lexical results as documents only. Retry resolves the failed turn in the visible conversation.

## Verification

The isolated backend was v1.1.0 on `127.0.0.1:8117`, started with both `TANTARA_DATA_DIR=/tmp/tantara-r3-data.FMTHoR` and `DATABASE_URL=sqlite:////tmp/tantara-r3-data.FMTHoR/tantara.db`; Alembic reached head and `scripts/seed.py --demo` reported “Demo workspace already seeded; researcher workspace reconciled.” The frontend used `127.0.0.1:3014`; our processes were stopped after verification.

The normal generation configuration was `MiniCPM5-2B` at `http://192.168.0.101:8080/v1`; `/settings/ai.runtime_status.reachable` reported `true` before the runs. The grounded-answer and genuine insufficiency tests completed with that model reachable. The unavailable test temporarily pointed settings at a dead local endpoint, asserted `model_unavailable`, no rendered answer, no model attribution, and evidence-only retrieval, then restored the prior model and verified Retry generated a grounded response. The `/ai/status` `ok` field was not treated as reachability proof.

Commands and outcomes:

- `pnpm format` — passed.
- `pnpm lint` — passed with no ESLint warnings or errors.
- `pnpm typecheck` — passed.
- `pnpm build` — passed; `/research` built at 9.29 kB.
- `TANTARA_WEB_URL=http://127.0.0.1:3014 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8117 pnpm test:e2e` — 13 passed, 4 failed (17 total). All 8 Research tests passed, covering formatter/grouping/status units, mobile shell bounds and navigation, scoped history, history/saved restoration, citations, no-evidence, genuine insufficiency, model-unavailable, and retry. The 4 failures are in the unrelated existing `smoke.spec.ts`: route traversal is interrupted by navigation at `/cases/case-1`; the settings smoke expects a Profile nav entry and a “Test connection” control not present in this tree; the dashboard smoke hardcodes port 8010. These tests were left unchanged.
- `TANTARA_WEB_URL=http://127.0.0.1:3014 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8117 pnpm exec playwright test tests/research.spec.ts --grep 'new research' --workers=1` — 1 passed after the scoped-history fix.

After the last valid full run, a final assertion was added for the mobile menu button’s viewport bounds. A focused rerun could not be completed: port 3014 had been taken by the `fe5` worktree and `/research` returned 404. That foreign process was not stopped or used. The earlier mobile run covered the navigation button and nine destinations; the new explicit button-bounds assertion is the only unverified test edit.

## Captures

Authenticated captures use real seeded API data, have no loading skeletons or Next.js dev badge, and are under `frontend/docs/screenshots/`.

- Desktop (1440px wide): `research-desktop-answer-citations.png` (historical capture, not in the current corpus), ``research-desktop-answer-citations.png` (historical capture, not in the current corpus)`, `research-desktop-insufficient-evidence.png` (historical capture, not in the current corpus), ``research-desktop-insufficient-evidence.png` (historical capture, not in the current corpus)`, `research-desktop-model-unavailable.png` (historical capture, not in the current corpus), ``research-desktop-model-unavailable.png` (historical capture, not in the current corpus)`, and `research-desktop-no-evidence.png` (historical capture, not in the current corpus).
- Mobile (390×844): ``research-desktop-no-evidence.png` (historical capture, not in the current corpus)`, `research-desktop-scope-selected.png` (historical capture, not in the current corpus), ``research-desktop-scope-selected.png` (historical capture, not in the current corpus)`, `research-desktop-history-refreshed.png` (historical capture, not in the current corpus), and ``research-desktop-history-refreshed.png` (historical capture, not in the current corpus)` (composer visible in the initial view).
- Additional interaction captures cover the citation destination, refreshed/restored history, saved answer, scope, library, suggestion, Ask, and Retry states.

The citation click reaches `/documents/{id}?page=N&chunk=...` and the viewer title matches the cited document. **The page-scroll/highlight handoff remains blocked by the Documents viewer:** this v1.1.0 `/api/v1/documents/{id}/pages` response is `{ "pages": [...] }`, while the current viewer only consumes a bare array or `{ "items": [...] }`. It consequently renders no `#page-N` element and has no “Page number” input. The Research lane did not change the Documents feature, and no claim is made that the cited page or chunk highlight was visible in the viewer capture.

The current v1.1.0 `/api/v1/ai/ask` response includes status, answer, citations with page/excerpt/title and score aliases, model, and disclaimer, but does not return the additive `supports`, `answer_basis`, `context_fields`, `conflicts`, or `insufficient_evidence` fields. The conditional UI behavior for those fields therefore needs a backend-enabled integration run.

## Changed files and commits

Each changed file is committed separately.

- Implementation and tests: `ca726a2` Research page; `4989fb7` Research CSS; `975b76c` shell navigation; `529136a` API types; `99fa2b6` presentation helpers; `168bfd5` Research tests; `cb93b94` Playwright assigned-URL configuration.
- Captures: `4f6f666` desktop answer; `064e07f` desktop empty; `5ebb44c` desktop insufficiency; `df22c50` desktop model unavailable; `f5cb4c8` desktop no evidence; `afa3f6b` mobile answer; `d1245d1` mobile empty; `db47805` mobile insufficiency; `c061a40` mobile model unavailable; `4b79258` mobile no evidence; `32318ad` Ask; `73e84d2` citation viewer; `e0ebf12` history entry; `2e64625` history refresh; `2b5127c` library; `f89d14a` new after history; `754fb84` new state; `12b9afe` retry recovered; `64190e6` saved answer opened; `e40fe00` saved answer; `d56e39d` scope; `c4a2e4d` suggested question; `685c298` restored session.
- This report is committed separately after the implementation and capture commits.

## L5d — citations, source provenance, and library controls

### Changes

- Citation links now display the document title and page in both visible text and their accessible name, preserve the chunk id only in `data-chunk-id`, and use native same-origin anchors to reliably open `/documents/{id}?page=N&chunk=...`. Tap targets are at least 40px tall.
- Retrieved sources are grouped by document, with page links and one best-ranked excerpt per page. Identical excerpts inside a document are shown once; remaining pages identify where the same excerpt recurs. Relevance is shown to three decimals with rank and “relative to this query” wording.
- The source rail separates answer-linked material from other retrievals. If the API gives no support mapping or inline citation references, it labels the retrieval “Other retrieved material” and explains that the API did not identify supporting excerpts. It does not claim those hits support the answer.
- The current backend returns `answer_kind: "model_generated"` and `model: { provider: "local", model: "MiniCPM5-2B" }`, but no `generation_kind`. The UI uses the returned `answer_kind` as the machine provenance attribute, shows the model id, and labels the turn “Model response · review sources.” Responses without a model trace do not receive model attribution or the AI-generated disclaimer.
- New research tests confirm that previous turns, the history selection, and retrieved sources clear. Mobile capture helpers scroll focused states below the sticky header and assert their headings are in frame. The insufficient-evidence capture assertion now focuses the state card; that updated capture could not be regenerated because another worktree occupied 3014 at the end of the round (details below).
- The no-evidence action now opens the Research library. The library offers PDF, DOCX, TXT, and Markdown upload through the measured `POST /ingest/file` form contract (`file` and required `title`), polls `/api/v1/documents/{id}/job`, and refreshes the actual document list. A test PDF fixture is confined to `frontend/tests/fixtures/`.
- Added interaction evidence for mobile source expansion, citation arrival, copy feedback, PDF download, and the upload destination. The PDF test asserts a real browser download event with a `.pdf` filename; the upload test verifies the indexed document reaches `ready` and removes it afterward.

### Verification and runtime provenance

The isolated backend was v1.1.0 at `127.0.0.1:8114`, using `TANTARA_DATA_DIR=/tmp/tantara-l5d.tPndYi` and `DATABASE_URL=sqlite:////tmp/tantara-l5d.tPndYi/tantara.db`. Demo seeding produced 7 clients, 12 cases, and 8 indexed PDFs. The frontend used `127.0.0.1:3014`. Both processes were stopped after verification; neither port was left bound by this worktree.

Before the grounded-answer tests, `/api/v1/settings/ai` reported model `MiniCPM5-2B`, configured endpoint `http://192.168.0.101:8080/v1`, and `runtime_status.reachable: true`. The live ask response had `status: "ok"`, `answer_kind: "model_generated"`, that model id, citations, and the disclaimer. Grounded-answer and insufficiency checks ran with this endpoint reachable. The unavailable test intentionally changed the backend setting to `http://127.0.0.1:1/v1`, asserted `model_unavailable` with no answer text, then restored the original endpoint before Retry; Retry returned a grounded response. The UI never displays either endpoint.

Commands and results:

- `pnpm format:check` — passed.
- `pnpm lint` — passed; Next.js emitted only its existing `next lint` deprecation notice.
- `pnpm exec tsc --noEmit` — passed.
- `pnpm build` — passed; `/research` built at 10.3 kB and `/research/documents` at 3.09 kB.
- `TANTARA_WEB_URL=http://127.0.0.1:3014 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8114 pnpm exec playwright test tests/research.spec.ts --workers=1` — **9 passed**. The suite uses real API calls and no `page.route` interception.
- Focused upload verification — **1 passed**, including successful API upload, ingestion to `ready`, and cleanup.
- An initial `pnpm test:e2e -- tests/research.spec.ts` wrapper invocation selected the full 17-test tree; it was interrupted during Research test 5 before any unrelated smoke tests ran. The explicit lane-file command above is the completed result.

### Captures

All files are in `frontend/docs/screenshots/`; desktop captures use 1440px width and mobile captures use 390×844. The final successful lane run refreshed the desktop answer/citations, empty, history, scope, insufficient-evidence, no-evidence, unavailable, and retry captures; mobile answer/citations, empty, insufficient-evidence, no-evidence, and unavailable captures; and added:

- `research-desktop-empty.png` (historical capture, not in the current corpus)
- ``research-desktop-empty.png` (historical capture, not in the current corpus)`
- `research-mobile-answer-citations.png` (historical capture, not in the current corpus)
- ``research-mobile-answer-citations.png` (historical capture, not in the current corpus)`
- `research-mobile-insufficient-evidence.png` (historical capture, not in the current corpus)
- ``research-mobile-insufficient-evidence.png` (historical capture, not in the current corpus)`

The current `research-mobile-model-unavailable.png` (historical capture, not in the current corpus) remains from the earlier, clipped capture. I updated its Playwright capture to scroll the complete state card into view. After 3014 became free I tried the focused recapture, but the live ask returned `status: "error"` and “No indexed excerpt directly answers this question” instead of a genuine insufficiency response; I did not capture that as an insufficiency state. A prior complete lane run passed 9/9 before this capture-only assertion change; this later focused attempt failed before capture. This specific mobile PNG is stale evidence and needs replacement on a run where the configured model returns the genuine insufficiency state.

### Remaining integration gaps

- **Citation arrival/highlighting remains unproven.** Clicking a page-3 citation reliably reaches the document route with `page=3` and the chunk id, and the citation test checks the URL and document title. The viewer still renders the extracted pages as continuous text from page 1: `/api/v1/documents/{id}/pages` returns `{ "pages": [...] }`, while the Documents viewer consumes an array or `{ "items": [...] }`. It creates no selected `#page-N` article and does not highlight the chunk. The mobile arrival capture shows this limitation. I left the Documents lane route untouched; its owner must parse the `pages` envelope, select/scroll to the requested page, and highlight the `chunk` excerpt before the requested page-3 arrival assertion can pass.
- **Answer-to-excerpt trace is absent in this backend response.** This v1.1.0 `/api/v1/ai/ask` response does not include `supports`, `answer_basis`, or inline `[n]` markers. The UI therefore does not invent sentence-level citation markers and places returned excerpts under “Other retrieved material” with an explicit reason. Backend support metadata is needed before excerpts can be honestly promoted to “Sources for this answer.”
- **Library page styling remains an integration item.** `research/documents/page.tsx` imports the Research feature stylesheet, but after the shared `globals.css` shrink, legacy semantic classes used by the merged shell/library environment are absent and the library heading/list appear unstyled. I did not restore core CSS or edit another lane. Carry this into the integration review at `briefs/L10-integration.md`.
- That `briefs/L10-integration.md` path is not present in this `fe4` checkout, so I could not inspect its styling table directly.

### Push and commits

The mandatory pre-work push published the previously committed round-3 branch head `4cf644338b15959bbea6adfab97458ec493660af` to `origin/luna/frontend-research` before any L5d feature edits. L5d implementation files and each PNG were committed separately. Implementation commits: `4ff44e6`, `d63b86f`, `a9c19c6`, `8cefb9f`, `9c48f55`, `fb3a684`, `d7bc941`, `d09b295`. The 29 individual capture commits form the contiguous range `5430526` through `f7762ff`. The report commit follows separately. The final focused insufficiency attempt described above occurred after the successful complete lane run and is recorded separately from its 9/9 result.
