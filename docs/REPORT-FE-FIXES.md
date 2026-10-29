# TANTARA frontend review fixes

## Review findings and changes

| Finding | Change | Files | Verification |
| --- | --- | --- | --- |
| Shell identity was hardcoded as Workspace Advocate / Advocate / AM | Shell identity now comes from `/auth/me`; initials are derived from the returned name. Preview uses `Preview workspace` / `Read-only preview`. | `frontend/src/components/shell.tsx` | API fixture `/auth/me`; route E2E and loaded desktop/mobile dashboard screenshots. |
| Notification dot was unconditional | Removed the dot. The current API contract has no unread count, so no unread state is claimed. The notification menu shows real dashboard activity. | `frontend/src/components/shell.tsx` | Screenshot review and route smoke checks. |
| Knowledge collection control did nothing | Kept the control disabled and added an explanatory title and helper text because this API contract has no collection-list endpoint. The case and jurisdiction scopes remain functional. | `frontend/src/app/(workspace)/dashboard/page.tsx` | Dashboard route smoke test; disabled control is visible under Research scope. |
| Guest preview could still submit mutations | Shared API client rejects POST/PATCH/PUT/DELETE in preview (login is explicitly allowed). Mutating controls are disabled with sign-in explanations, including Ask, settings saves, and corpus import. | `frontend/src/lib/api/client.ts`, `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/(auth)/page.tsx` | E2E verifies guest Ask is disabled; all writes use the guarded API client. |
| Search and citation links could navigate to missing routes | Case and document detail routes now exist in this worktree; those links target those API-backed pages. The absent Research Desk remains an explanatory status instead of a dead link. | `frontend/src/app/(workspace)/cases/[id]/page.tsx`, `frontend/src/app/(workspace)/documents/[id]/page.tsx`, `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/components/shell.tsx` | Route smoke visits case/document routes; all routes returned without console or hydration errors. |
| Next dev indicator appeared in screenshots | Disabled Next dev indicators. | `frontend/next.config.ts` | Captured screenshots contain no dev indicator. |
| Home and sidebar imagery looked like flat clip-art | Replaced their backgrounds with a locally stored Commons photograph of Themis above Hong Kong's Old Supreme Court and added a dark overlay on the hero. The source is CC0 and its details are recorded. The hero is centered, the capability row has a hairline divider, and capability items are static white-icon descriptions. | `frontend/public/brand/legal-scales.jpg`, `frontend/public/brand/CREDITS.md`, `frontend/src/app/(auth)/page.tsx`, `frontend/src/app/globals.css`, `frontend/README.md` | Inspected the original downloaded photograph and the refreshed home/sidebar screenshots. |
| Dashboard hierarchy differed from the crop | Kept the four primary metrics in one row immediately above Ask TANTARA. Drafts and tasks now sit in a compact secondary strip after the Ask and recent-question areas. Filters are inside Research scope; recent questions are below the AI panel. | `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/app/globals.css` | Refreshed dashboard desktop/mobile screenshots and Playwright route checks. |
| Shell geometry and mobile header needed adjustment | Sidebar and workspace offsets are 224px. Under 1024px the sidebar becomes a drawer; at 760px and below the desktop search box is hidden and one 44px search trigger sits beside menu and bell. | `frontend/src/app/globals.css`, `frontend/src/components/shell.tsx` | E2E checks 360/768/1024/1440 widths and asserts one mobile search trigger; no horizontal overflow. |
| Local AI connection test was unreachable | Local AI now branches to the dedicated panel, shows the connection status row, and provides a 44px Test connection button that calls `/settings/ai` and `/ai/status`. Only allowlisted provider/model/latency/embedding fields render; secret keys are never printed. | `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/globals.css` | E2E checks status semantics and button presence; screenshot captures show the loaded form and status. |
| Accessibility issues in forms, search, and loading/error states | Email uses `type=email` and `autocomplete=username`; disclaimer contrast is `#64748B`; focus-within rings are visible; global search is one native button; settings validation uses matching error IDs and ARIA attributes; loading regions use `role=status`; offline instructions are in expandable details. | `frontend/src/app/(auth)/page.tsx`, `frontend/src/components/shell.tsx`, `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/app/(workspace)/cases/[id]/page.tsx`, `frontend/src/app/(workspace)/documents/[id]/page.tsx`, `frontend/src/app/globals.css` | Playwright asserts email attributes, settings `aria-invalid`/`aria-describedby`, status role, mobile search count, and route console/hydration health. |
| Preview badge overlapped sidebar artwork | Moved the badge into the topbar. | `frontend/src/components/shell.tsx`, `frontend/src/app/globals.css` | Screenshot inspection at desktop and mobile sizes. |
| Login page left a dead band on mobile | Home layout fills the desktop viewport; mobile hero is at least 340px, uses 20px padding, and stacks 44px CTAs. | `frontend/src/app/globals.css` | Refreshed home desktop/mobile screenshots. |
| Source was difficult to maintain | Added Prettier config and `pnpm format`; formatted all of `src/` in dedicated formatting commits. Checked-in local Inter and Playfair Display WOFF2 files make `next/font/local` builds work without fetching Google Fonts. | `frontend/.prettierrc.json`, `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/src/**`, `frontend/src/styles/fonts/**`, `frontend/README.md` | `pnpm format`; production build completed with local fonts. |

## Intentional deviations

- The attached sidebar/login crops show a warm still life with brass scales and law books. The Commons search did not yield a suitable exact match under the allowed Public Domain, CC0, or CC-BY licenses. I used the verified CC0 Hong Kong courthouse Themis photograph instead. It supplies real justice/scales photography and warm architectural tones, but it does not include books and its composition differs from the crops. This is the main remaining visual difference.
- The API contract has no collections-list endpoint, so “All collections” is disabled with an explanation instead of being sent as an inert `collection_id`.
- This phase has no Research Desk route. Its call-to-action is a clear availability note; dashboard actions for later-phase product areas remain disabled and labeled.
- Browser screenshots and E2E used `tests/api-fixtures.mjs`. A direct login probe to the local API succeeded, but its browser preflight did not return `Access-Control-Allow-Origin` for `http://127.0.0.1:3010`; the screenshot harness therefore used its test-only contract fixtures. The shipped app contains no fixtures and still calls the configured API.

## Quality gates

Executed from `frontend/`:

- `pnpm format` — passed.
- `pnpm lint` — passed, no ESLint warnings or errors (Next 15 prints its upstream deprecation notice for `next lint`).
- `pnpm typecheck` — passed (`tsc --noEmit`).
- `pnpm build` — passed; static and dynamic routes generated successfully with local font files.
- `pnpm test:e2e` — passed, 8 tests. Coverage includes all existing routes, console/hydration health, login validation and submission, settings validation ARIA, guest mutation controls, and 360/768/1024/1440 responsive widths.
- `pnpm screenshots` — passed, 6 loaded screenshots captured with no browser console/page errors.

## Screenshot artifacts

- `home-desktop.png` (historical capture, not in the current corpus)
- ``home-desktop.png` (historical capture, not in the current corpus)`
- `home-mobile.png` (historical capture, not in the current corpus)
- ``home-mobile.png` (historical capture, not in the current corpus)`
- `dashboard-desktop.png` (historical capture, not in the current corpus)
- ``dashboard-desktop.png` (historical capture, not in the current corpus)`

## Remaining phase work

Cases collection, Research Desk, Drafts, Calendar, Tasks, Clients, Community, and bundle workflows still belong to later phases. Dashboard quick actions for those unavailable flows are disabled and labeled. Institution editing and embedding rebuild are also read-only/unavailable because the current contract does not expose write operations for them.

## Commit organization

Every commit in this review is file-scoped. The Prettier-only pass is isolated in 17 formatting commits (`7b9ef4b` through `84d4b36` in chronological order); implementation, license/font, and tooling changes each have their own file commit. The six screenshots are also committed individually: `f11c5c8`, `059fec3`, `239a81f`, `6ca665d`, `0a74c48`, and `0e44d30`. The review report is committed separately.
