# TANTARA Frontend Fixes — Sol Round 2

## Findings and changes

| Sol finding | Change | Files | Verification |
| --- | --- | --- | --- |
| Dashboard columns and summary hierarchy | Rebuilt the dashboard body as independent main and side columns. The right side starts with the empty `dashboard-matters` integration slot, then upcoming hearings. Drafts in Progress and Tasks Due now share one full-width summary card. | `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/src/app/globals.css` | Dashboard desktop/mobile captures; responsive Playwright checks at 360, 768, 1024 and 1440px. |
| Unavailable metrics must not become zero | Primary and secondary metrics display an em dash while loading, after summary errors, or when a response omits a value. | `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/tests/smoke.spec.ts` | Fixture-backed 503 test asserts four primary metric values are `—`. |
| Remove dead Quick actions and roadmap text | Deleted the six disabled “coming soon” controls and the later-phase Research Desk sentence. Added the plain-text availability note and kept the recent-question empty state direct. | `frontend/src/app/(workspace)/dashboard/page.tsx`, `frontend/tests/smoke.spec.ts` | E2E asserts there are no “coming soon” buttons and confirms the static note. |
| Home composition, contrast and mark | Applied the full-photo scrim, centered welcome and subtitle, a full-width dark capability band, compact desktop hero sizing and the ribbon T mark. Kept the 340px mobile minimum and raised the disclaimer to 12px/1.5. | `frontend/src/app/(auth)/page.tsx`, `frontend/src/app/globals.css`, `frontend/src/components/shell.tsx`, `frontend/public/brand/t-mark.svg` | Refreshed Home desktop/mobile captures; login validation test. |
| Sidebar image protection | Added the requested upward navy scrim across the entire photo block, with white serif heading and `#cbd5e1` supporting copy at 12px/1.5. | `frontend/src/app/globals.css` | Dashboard desktop/mobile captures. |
| Mobile global search entry | Kept the wide search control hidden at mobile widths and made the one labelled topbar trigger 44×44px beside the menu, bell and profile. | `frontend/src/app/globals.css`, `frontend/tests/smoke.spec.ts` | E2E at 390px asserts one visible “Open global search” button; Local AI mobile capture shows the control. |
| Local AI feedback and test scope | Added a concise status line for reachability, model, latency and embeddings health; put JSON diagnostics in a collapsed Technical details disclosure; redacted secret-like keys; and clarified that Test connection checks saved configuration. The implementation uses the contract’s GET `/settings/ai` and GET `/ai/status`. | `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/globals.css`, `frontend/tests/smoke.spec.ts` | E2E checks the status region, Technical details disclosure and helper association; Local AI desktop/mobile captures show the summary and collapsed disclosure. |
| Settings mobile navigation | Added horizontal scroll, 44px minimum link height, trailing fade, and auto-scroll of the selected section with reduced-motion handling. | `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/globals.css` | Local AI mobile capture and 360/768px responsive checks. |
| Type, contrast and field descriptions | Kept metric text fully opaque, raised the Home disclaimer size, and joined stable help/error IDs in Settings `aria-describedby`. Login validation errors now set `aria-invalid` and point to their inline messages. | `frontend/src/app/(auth)/page.tsx`, `frontend/src/app/(workspace)/settings/[section]/page.tsx`, `frontend/src/app/globals.css`, `frontend/tests/smoke.spec.ts` | E2E asserts login and Settings error attributes plus Local AI help association. |

## Focus, validation and recovery evidence

The screenshot harness now records keyboard focus on both the global search button and Ask TANTARA input, invalid-email/short-password validation, and the offline panel with its technical command expanded. It then restores the API fixture, retries, and confirms metrics load again.

The backend was not available to the browser capture harness with the needed local CORS/auth setup, so these screenshots use the existing Playwright-only API fixtures. The shipped frontend contains no fixture data and continues to call the configured API. The offline-recovery screenshot is a paired sequence: `states-offline-desktop.png` records the expanded offline state and `states-offline-recovered-desktop.png` records the successful retry.

## Intentional scope decisions

- The target case-management crop contains a populated table, but this phase explicitly requires an empty `<section className="matters-slot" data-slot="dashboard-matters" />` for the case-module integrator and prohibits fabricated case rows. That slot is present, before Upcoming hearings in the right column. No table contents were invented.
- No other Sol finding was rejected.

## Gates and capture results

Command chain: `pnpm format && pnpm lint && pnpm typecheck && pnpm build && pnpm test:e2e`

- `pnpm format`: passed; formatted the full `src/` tree.
- `pnpm lint`: passed with no ESLint warnings or errors (Next.js notes that `next lint` is deprecated for a future major release).
- `pnpm typecheck`: passed (`tsc --noEmit`).
- `pnpm build`: passed; Next.js generated all application routes.
- `pnpm test:e2e`: **9 passed**, including route/console/hydration checks, login and settings validation, offline metrics, mobile search, and 360/768/1024/1440px responsive checks.
- `pnpm screenshots`: passed; **11 captures** generated with logged-in fixture identity and loaded data.

Screenshot paths:

- `docs/screenshots/home-desktop.png`
- `docs/screenshots/home-mobile.png`
- `docs/screenshots/dashboard-desktop.png`
- `docs/screenshots/dashboard-mobile.png`
- `docs/screenshots/settings-local-ai-desktop.png`
- `docs/screenshots/settings-local-ai-mobile.png`
- `docs/screenshots/states-focus-desktop.png`
- `docs/screenshots/states-ai-input-focus-desktop.png`
- `docs/screenshots/states-validation-desktop.png`
- `docs/screenshots/states-offline-desktop.png`
- `docs/screenshots/states-offline-recovered-desktop.png`

## Visual fidelity self-assessment: Dashboard vs `frontend.png`

The desktop capture matches the target’s four primary metrics, their icon/color roles, indigo Ask TANTARA panel, white input and suggestion chips, compact navy sidebar, rectangular search, and warm legal photography. The new right column establishes the case-module slot before the hearings card; the secondary totals read as one grouped summary card. The mobile capture preserves loaded metrics, research controls and hearings without page-wide overflow.

The dashboard remains less dense than the reference board. The case table itself is deliberately absent until the integrator inserts the real cases module, and the case slot therefore leaves the right rail visually sparse compared with the target’s populated Case Management card. The shell currently exposes only Dashboard and Settings in navigation because those are the built destinations in this worktree. These are scope differences, not substitute sample data.
