# TANTARA Frontend

Next.js 15 App Router workspace shell for the local TANTARA arbitration API. The interface uses Inter and Playfair Display, Tailwind CSS tokens, Lucide icons, TanStack Query v5, React Hook Form/Zod, Sonner, Framer Motion animations with reduced-motion support, and Playwright. App code only calls the configured API; offline response fixtures are under `tests/` and are not imported by the application.

## Local setup

```bash
cd frontend
pnpm install
pnpm exec playwright install chromium
pnpm dev
```

The frontend binds to `127.0.0.1:3010`. Set `NEXT_PUBLIC_API_BASE_URL` in `.env.local` to change the API origin; the default is `http://127.0.0.1:8010`. The API base path `/api/v1` is added by the client. Local development credentials: `advocate@tantara.local` / `tantara-local`.

## Commands

| Command                                                                         | Purpose                                                                     |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `pnpm dev`                                                                      | Start Next dev server on `127.0.0.1:3010`                                   |
| `pnpm build`                                                                    | Production build                                                            |
| `pnpm start`                                                                    | Serve production build on `127.0.0.1:3010`                                  |
| `pnpm lint`                                                                     | Run Next ESLint checks                                                      |
| `pnpm format`                                                                   | Format the complete `src/` tree with Prettier                               |
| `pnpm typecheck`                                                                | Run strict TypeScript checks                                                |
| `pnpm test:e2e`                                                                 | Route, login, settings, responsive, console, and hydration smoke checks     |
| `pnpm screenshots`                                                              | Capture `/`, `/dashboard`, `/settings/local-ai` at desktop and mobile sizes |
| `pnpm screenshots -- --routes=/dashboard,/settings/profile --viewport=1440x900` | Select screenshot routes and desktop viewport                               |
| `pnpm gen:api`                                                                  | Refresh the checked-in API schema when the backend OpenAPI endpoint is live |

Screenshot output is committed under `../docs/screenshots/`. Desktop images are 1440 CSS pixels wide with device scale factor 2; mobile images are 390×844 CSS pixels.

## Design tokens

| Token                      | Value                             | Use                                     |
| -------------------------- | --------------------------------- | --------------------------------------- |
| Midnight                   | `#0A1730` → `#06101F`             | Sidebar and hero surfaces               |
| Indigo                     | `#4F46E5` → `#4338CA`             | Primary actions and selected navigation |
| AI panel                   | `#3B3D9B` → `#4B3AA8` → `#5B3FC4` | Research prompt panel                   |
| Workspace                  | `#F6F7F9`                         | Main page background                    |
| Ink                        | `#0F172A`                         | Main text                               |
| Muted                      | `#64748B`                         | Supporting text                         |
| Border                     | `#E7EAF0`                         | Cards and dividers                      |
| Gold                       | `#C6A15B`                         | Small brand and illustration accents    |
| Success / warning / danger | `#16A34A` / `#D97706` / `#E11D48` | Status feedback                         |

## Routes

| Route                   | State                                                                                       |
| ----------------------- | ------------------------------------------------------------------------------------------- |
| `/`                     | Login, advocate sign-in, and read-only preview entry                                        |
| `/dashboard`            | API-backed summary, Ask TANTARA, upcoming calendar, activity, and quick-action availability |
| `/settings/profile`     | Profile settings                                                                            |
| `/settings/workspace`   | Workspace settings                                                                          |
| `/settings/local-ai`    | Local model configuration and live status check                                             |
| `/settings/embeddings`  | Embedding configuration/status and rebuild action                                           |
| `/settings/database`    | Database metadata and backup download                                                       |
| `/settings/data-import` | Corpus import trigger/status                                                                |
| `/settings/appearance`  | Theme, density, and font preference                                                         |
| `/settings/security`    | Audit/security information and password change                                              |

Navigation only exposes routes present in this phase. Cases, Research, Drafts, Calendar, Tasks, Clients, Community, document previews, and filing bundles are planned for later phases and are not represented as working routes yet.

## Complete in this phase

- Responsive shell, accessible active navigation, command search (`Ctrl-K` / `⌘K`), account menu, login, guest preview, API client, query defaults, offline/error handling, dashboard, eight Settings paths, original SVG legal illustrations, screenshots, and Playwright smoke harness.
- All dashboard metrics are read from `/dashboard/summary`; workspace data lists and settings are read from their API endpoints. E2E and screenshot checks use the running backend; no API fixtures are installed in the browser.

## Pending integration

- Pages for later product areas are not implemented in this phase. Dashboard quick actions that depend on them are visibly disabled.
- The backend brief requests a full user profile/auth contract and institutional management; settings render the backend data available through the contract, while institution editing awaits a write endpoint.
- The checked-in `src/lib/api/schema.ts` is a compact fallback snapshot. `pnpm gen:api` replaces it with the complete live OpenAPI document when the backend is available.

## Playwright integration environment

`pnpm test:e2e` starts one isolated backend and one frontend. The backend is migrated and seeded with `scripts/seed.py --demo` in a fresh temporary data directory that is removed after the run. Tests use `TANTARA_API_ORIGIN` as their sole backend origin variable; the frontend proxies `/api/v1` to that origin, so browser requests remain same-origin. `TANTARA_API_PORT`, `TANTARA_WEB_PORT`, and `TANTARA_WEB_URL` can select alternate local ports. `TANTARA_PYTHON` can select the backend Python executable. `TANTARA_TEST_DATA_DIR` can select an explicit data directory, which is retained after the run.

`TANTARA_WORKSPACE_TIME_ZONE` is the shared server and browser display zone (default `Asia/Kolkata`). Datetime inputs carry that zone's offset in API payloads; stored wall times are returned with the same offset. Playwright pins its browser to UTC to catch host-timezone regressions. The calendar keeps its existing bare-array response by default for API compatibility; callers that need pagination metadata can request `?envelope=true` for `{items,total,page,page_size,pages}`.

The default test ports are `8011` for the API and `3011` for the frontend. Existing application development commands continue to use port `3010`.

## Third-party licenses

`public/brand/legal-scales.jpg` is a locally stored Wikimedia Commons photograph by Scotted400, dedicated to the public domain under CC0. Source details are recorded in `public/brand/CREDITS.md`; no image is hotlinked.

Inter and Playfair Display are served from checked-in Latin WOFF2 files through `next/font/local`, so production builds do not need to fetch Google Fonts. Both are licensed under the SIL Open Font License 1.1; the complete license texts are in `src/styles/fonts/`.
