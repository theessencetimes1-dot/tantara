# Community and corpus import verification

Date: 2026-10-28  
Branch: `luna/frontend-community`

## Routes and implementation

| Route                    | File                                                                                                                    | Change                                                                                                                                                                                                                                                                                                                                                                             | Verification and observed responses                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/community`             | `frontend/src/app/(workspace)/community/page.tsx`, `frontend/src/features/community/Community.tsx`                      | Feed with API ordering and pagination, server search/tag filters, real case links, demo and visibility labels, and a composer that refreshes from the API after submit. Search errors keep a working retry action.                                                                                                                                                                 | `seeded feed, navigation, and tag filter render at desktop and mobile sizes`: list/search/tag requests returned 200. `composer success is confirmed by a fresh API list response and validation errors are inline`: create returned 200 and the follow-up list contained the new title and author; overlong title returned 422 with `validation_error` and the title field message.        |
| `/community/[id]`        | `frontend/src/app/(workspace)/community/[id]/page.tsx`, `frontend/src/features/community/Community.tsx`                 | Thread with API author names, UTC timestamps, demo/visibility labels, reply total from the paginated replies response, reply composer, persisted save/unsave state, and honest errors. No unsupported post deletion control is shown.                                                                                                                                              | `thread shows API authors and real reply total at desktop and mobile sizes`: detail and replies returned 200. `reply submission at mobile width increments the API total by exactly one`: reply POST and subsequent replies GET returned 200; response total increased by one. `saved thread remains saved after reload`: save POST returned 200; saved filter remained true after reload. |
| `Community` sidebar link | `frontend/src/components/shell.tsx`                                                                                     | Added one-click Community navigation and active state for feed and thread routes. The sidebar keeps only links whose routes exist in this worktree.                                                                                                                                                                                                                                | `seeded feed, navigation, and tag filter render at desktop and mobile sizes`: clicking Community opened the feed and set `aria-current="page"`.                                                                                                                                                                                                                                            |
| `/settings/data-import`  | `frontend/src/features/settings-data/CorpusImportPanel.tsx`, `frontend/src/app/(workspace)/settings/[section]/page.tsx` | Loads and renders the API manifest, confirms the internet-backed import, polls through stale/queued state until a fresh terminal manifest appears, and shows each source status and importer reason as returned. The API does not return a data directory or index size, so the UI says so; it documents the real `scripts/rebuild_index.py` command without a fake action button. | `corpus import panel renders the live response shape`: GET returned 200 with `{status, items}`. `public corpus import is accepted, polled, and displays recorded outcomes`: POST returned 202; a fresh GET returned `status: complete`.                                                                                                                                                    |

`frontend/src/features/community/api.ts` contains feature-local endpoint wrappers. Observed post item keys were: `author`, `author_name`, `author_role`, `body`, `case_ref`, `created_at`, `id`, `is_demo`, `kind`, `tags`, `title`, `updated_at`, `visibility`. The `author` object contains `display_name` and `role`; post rows do not contain an author ID. The “posted by you” marker therefore requires both author name and role to match `/auth/me`.

The create request uses the measured fields `title`, `body`, `kind`, `visibility`, `tags`, and optional `case_ref`. It never sends the obsolete `case_id` field. Case choices come from `GET /api/v1/cases?page_size=100`, and rendered case titles link to their real case route. Tags in the filter come from returned post tags. Save is the API toggle operation; saved state is re-read from `GET /api/v1/community/posts?saved=true` after reload.

## Live authorization and endpoint evidence

The backend was started from `/home/kahitoz/projects/tantara-wt/be/backend` with both isolation variables set, `CORS_ORIGINS=http://localhost:3016,http://127.0.0.1:3016`, and bound only to `127.0.0.1:8117`. Frontend requests used `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8117`. Three seeded users were exercised.

| Request                                                              | Observed status | Evidence                                                                                                              |
| -------------------------------------------------------------------- | --------------: | --------------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/community/posts` without a token                        |             401 | Authorization test.                                                                                                   |
| `GET /api/v1/community/posts?page=1&page_size=100` with advocate     |             200 | Real paginated list and item shape.                                                                                   |
| `GET /api/v1/community/posts?q=Demo` and `?tag=construction`         |             200 | API search and real tag filtering.                                                                                    |
| `POST /api/v1/community/posts`                                       |             200 | Composer and visibility tests.                                                                                        |
| `POST /api/v1/community/posts` with title over 300 characters        |             422 | Inline `validation_error`; title error came from `details`.                                                           |
| `GET /api/v1/community/posts/{pid}` as an authorized reader          |             200 | Thread and workspace visibility tests.                                                                                |
| `GET /api/v1/community/posts/{private_pid}` as another user          |             404 | Private detail is rejected by the API. The post ID was also absent from that user’s list.                             |
| `GET /api/v1/community/posts/{pid}/replies`                          |             200 | Reply count and chronology came from the response envelope.                                                           |
| `POST /api/v1/community/posts/{pid}/replies`                         |             200 | Reply composer.                                                                                                       |
| `DELETE /api/v1/community/posts/{pid}/replies/{rid}` by another user |             403 | The reply owner restriction was enforced.                                                                             |
| `DELETE /api/v1/community/posts/{pid}/replies/{rid}` by its author   |             200 | Owner deletion succeeded.                                                                                             |
| `POST /api/v1/community/posts/{pid}/save`                            |             200 | Response toggled `{saved: true}` / `{saved: false}`. Advocate and researcher saved lists were verified independently. |
| `GET /api/v1/auth/me`                                                |             200 | Identity loaded before authenticated captures.                                                                        |
| `GET /api/v1/cases?page_size=100`                                    |             200 | Real case choices and case titles.                                                                                    |
| `GET /api/v1/settings/data/import`                                   |             200 | Initial response was `{status: "not_imported", items: []}`; later response contained the manifest.                    |
| `POST /api/v1/settings/data/import`                                  |             202 | Returned queued import; the UI then polled the manifest endpoint.                                                     |

The API permits another user to read a `workspace` post (200); `private` posts are owner-only (404 to another user). Saved state is per-user. The staff seed account has shared workspace posts visible under the new visibility rules; its unfiltered feed was not empty. The captured empty state is therefore an honest no-match search (`total: 0`), not a claim that the unfiltered staff feed is empty.

## Corpus import outcome

The importer completed and wrote a seven-item manifest. On the first run UNCITRAL was indexed. The verification rerun recorded it as `already_indexed`. The final manifest contained one indexed/already-indexed source and six failures:

| Source                                                            | Final status                                          | Recorded reason                                                                                                                                                                                                                                                                                                   |
| ----------------------------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| UNCITRAL Arbitration and Conciliation                             | `already_indexed` (it was `indexed` on the first run) | —                                                                                                                                                                                                                                                                                                                 |
| Arbitration and Conciliation Act, 1996 (Wikisource transcription) | `failed`                                              | `HTTPStatusError: Client error '403 Please respect our robot policy https://w.wiki/4wJS. If you think you are incorrectly blocked, please contact noc@wikimedia.org (768589d)' for url 'https://en.wikisource.org/wiki/Arbitration_and_Conciliation_Act,_1996'` followed by the importer’s recorded `For` suffix. |
| LCIA Arbitration Rules                                            | `failed`                                              | `PermissionError: robots.txt disallows this URL`                                                                                                                                                                                                                                                                  |
| Official legislation portal probe (India Code)                    | `failed`                                              | `ReadTimeout: The read operation timed out`                                                                                                                                                                                                                                                                       |
| Official court portal probe (Supreme Court of India)              | `failed`                                              | `Connection failure: source was unreachable from this host`                                                                                                                                                                                                                                                       |
| Institution portal probe (SIAC)                                   | `failed`                                              | `Connection failure: source was unreachable from this host`                                                                                                                                                                                                                                                       |
| Archive mirrors probe (Internet Archive)                          | `failed`                                              | `ValueError: Response did not contain enough readable source text`                                                                                                                                                                                                                                                |

The importer stores the full reasons in the manifest; the panel renders the returned strings without replacing them with generic success copy. For the verification run, `TANTARA_DATA_DIR` was `/tmp/l8b-data`; the on-disk index directory was `/tmp/l8b-data/index` (75,693 bytes at inspection). The API response does not include these path/size values, which is why the panel marks them “Not reported by this API.” The real rebuild command is documented in the panel: `TANTARA_DATA_DIR=/path/to/data DATABASE_URL=sqlite:////path/to/data/tantara.db backend/.venv/bin/python scripts/rebuild_index.py` from the repository root.

## Playwright captures

All captures used authenticated accounts and live API responses. No API responses were stubbed; no `-fixture` captures were created. Viewports were set explicitly per test. `fullPage` screenshots retain the stated viewport width/height but extend vertically to include the full state.

| Capture                                                                | Viewport / state                                                                      | API evidence                                                                        |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `captures-fe7/community-feed-seeded-desktop-1440x900.png`              | Desktop 1440×900, seeded demo search results                                          | `GET /community/posts?q=Demo`                                                       |
| `captures-fe7/community-feed-seeded-mobile-390x844.png`                | Mobile 390×844, seeded demo search results                                            | `GET /community/posts?q=Demo`                                                       |
| `captures-fe7/community-feed-filtered-construction-mobile-390x844.png` | Mobile 390×844, construction tag selected                                             | `GET /community/posts?tag=construction`                                             |
| `captures-fe7/community-detail-replies-desktop-1440x900.png`           | Desktop 1440×900, seeded post and replies                                             | `GET /community/posts/{pid}`, `GET /community/posts/{pid}/replies`                  |
| `captures-fe7/community-detail-replies-mobile-390x844.png`             | Mobile 390×844, same seeded thread                                                    | Same detail and replies GETs                                                        |
| `captures-fe7/community-composer-success-desktop-1440x900.png`         | Desktop 1440×900, successful workspace post refreshed from API                        | `POST /community/posts`, then `GET /community/posts`                                |
| `captures-fe7/community-composer-validation-desktop-1440x900.png`      | Desktop 1440×900, server validation failure shown inline                              | `POST /community/posts` → 422                                                       |
| `captures-fe7/community-reply-submitted-mobile-390x844.png`            | Mobile 390×844, reply and incremented total                                           | `POST /community/posts/{pid}/replies`, then `GET /community/posts/{pid}/replies`    |
| `captures-fe7/community-empty-search-staff-desktop-1440x900.png`       | Desktop 1440×900 viewport, full-page no-match search state                            | `GET /community/posts?q=no-match-community-verification-20261028`, 200 with total 0 |
| `captures-fe7/community-offline-error-desktop-1440x900.png`            | Desktop 1440×900, API stopped after authentication; Retry recovered after API restart | Failed feed GET, then successful `GET /community/posts` on retry                    |
| `captures-fe7/community-saved-persisted-desktop-1440x900.png`          | Desktop 1440×900, saved state after reload                                            | `POST /community/posts/{pid}/save`, `GET /community/posts?saved=true`               |
| `captures-fe7/settings-data-manifest-desktop-1440x900.png`             | Desktop 1440×900, live manifest                                                       | `GET /settings/data/import`                                                         |
| `captures-fe7/settings-corpus-import-running-desktop-1440x900.png`     | Desktop 1440×900, accepted import / polling state                                     | `POST /settings/data/import` → 202                                                  |
| `captures-fe7/settings-corpus-import-result-desktop-1440x900.png`      | Desktop 1440×900 viewport, full terminal manifest                                     | `GET /settings/data/import`                                                         |
| `captures-fe7/settings-corpus-source-indexed-desktop-1440x900.png`     | Desktop 1440×900, UNCITRAL `already_indexed` result                                   | `GET /settings/data/import`                                                         |
| `captures-fe7/settings-corpus-source-failed-desktop-1440x900.png`      | Desktop 1440×900, a failed source with the recorded reason                            | `GET /settings/data/import`                                                         |

## Gates and remaining limits

Final verification results:

- `pnpm exec tsc --noEmit`: pass, 0 diagnostics.
- `pnpm lint`: pass, 0 ESLint warnings/errors. Next printed its existing `next lint` deprecation notice.
- `pnpm format:check`: pass, all 9 scoped source/config/test paths checked by the script.
- `pnpm build`: pass; `/community` and `/community/[id]` compiled as static-shell and dynamic routes respectively.
- `git diff --check`: pass, 0 whitespace errors.
- `pnpm exec playwright test tests/community.spec.ts`: 10 passed, 0 failed, 0 skipped in the final run. It covered the ten named tests above, including auth, private visibility, foreign reply deletion, per-user saves, import start/result, and offline recovery.

Earlier iteration failures were corrected before the final run: a strict locator matched multiple validation alerts, the staff feed expectation incorrectly assumed workspace posts were hidden, and the offline retry assertion expected a post despite a retained no-match query. The final suite reports no failures.

Remaining limits: this worktree has only Dashboard, Community, and Settings route entries available for the sidebar; the other six links in the sibling worktree’s nine-item navigation have no routes here, so adding them would create dead links. The seed exposes no unfiltered empty account after workspace posts are shared, so the empty screenshot uses a real no-match query. The import endpoint does not return storage/index metadata; those values are not fabricated in the panel. On the final verification run, one public source was already indexed and six source probes failed as listed above.

## Commits

Round 1 commits already present on this branch: `670c8e3`, `2685236`, `db2ce55`, `0808e78`, `56b12a1`, `af80ec6`.

Round 2 commits (one changed file per commit):

- `91197e7` scoped format check command
- `e9ca0a3` Playwright port/config
- `84a5fdf` Community sidebar navigation
- `6a5f88b` Community API wrappers
- `181bbe5` Community feed and thread UI
- `1ed2211` corpus import panel
- `a3b87d8` live Community and corpus tests
- `84b731a`, `184cec3`, `e432692` feed captures
- `21bcbd7`, `efc4845` thread captures
- `e7e2fd2`, `1853f55` composer captures
- `843d0a7` reply capture
- `0a340da` empty state capture
- `536cc5e` offline capture
- `2e3f329` saved state capture
- `8e8cbf5`, `b82d54d`, `9f9f083`, `c6a1eb8`, `e92e6f0` corpus captures
- This report is added in its own single-file commit.
