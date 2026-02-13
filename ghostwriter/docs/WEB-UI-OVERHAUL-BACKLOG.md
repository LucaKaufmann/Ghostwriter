# Ghostwriter Web UI Overhaul - Implementation Backlog

Last updated: 2026-02-13
Owner: Frontend
Status: Completed

Release validation and rollout notes: `ghostwriter/docs/WEB-UI-RELEASE-CHECKLIST.md`

## Goals
- Ship a production-ready dark mode with `light` / `dark` / `system` support and no flash on load.
- Improve task completion speed for the top workflows: trigger digest, manage feeds, read digest content, configure schedules.
- Reduce UI complexity and maintenance cost by splitting oversized route files into reusable feature modules.
- Raise baseline quality for accessibility, visual consistency, and regression safety.

## Non-goals
- Backend feature expansion unrelated to UI/UX overhaul.
- Native mobile app changes.
- Full visual rebrand of logos/marketing site.

## Baseline Risks Identified
- No active theme controller despite existing dark tokens.
- Very large route files (settings/feeds/dashboard/reader) increase regression risk.
- Repeated date/status/download helper logic across pages.
- Mixed semantic and hardcoded color classes make dark mode brittle.
- No frontend test suite for UI regressions.

## Global Definition of Done
A ticket is done only when all are true:
- `npm run check` passes.
- `npm run build` passes.
- Accessibility checks for changed flows are completed (keyboard + screen reader labels + contrast).
- Light and dark theme behavior is validated for touched surfaces.
- User-facing behavior changes are documented in `ghostwriter/README.md` if needed.

## Milestone Plan
- M1 Foundation + Theme: FE-001 to FE-006
- M2 IA + Core Workflow UX: FE-010 to FE-045
- M3 Quality + Rollout: FE-070 to FE-100

## Ticket Index
| ID | Priority | Estimate | Title | Depends on |
|---|---|---:|---|---|
| FE-001 | P0 | 2d | Theme runtime, persistence, no-flash boot | - |
| FE-002 | P0 | 1.5d | Semantic status tokens and color cleanup | FE-001 |
| FE-003 | P1 | 1d | Shared date/format/download utility extraction | - |
| FE-004 | P1 | 1d | Remove debug logging and tighten auth state UX | - |
| FE-005 | P0 | 2d | Componentization scaffold for oversized routes | FE-003 |
| FE-006 | P1 | 0.5d | Product-specific frontend README and contributor guide | - |
| FE-010 | P0 | 3d | Settings IA split (tabs/subroutes + grouped sections) | FE-005 |
| FE-020 | P1 | 2d | Dashboard workflow redesign (action-first, clearer status) | FE-005 |
| FE-030 | P1 | 2.5d | Feeds UX overhaul (filters, bulk actions, safer edits) | FE-005 |
| FE-040 | P1 | 2d | Digests list UX overhaul (filters/sort/pagination/actions) | FE-005 |
| FE-045 | P1 | 2d | Reader experience upgrade (readability controls + dark prose) | FE-001, FE-005 |
| FE-050 | P2 | 1d | Newsletters page clarity and state messaging refresh | FE-002 |
| FE-060 | P2 | 1d | App shell/nav improvements (quick actions + theme toggle placement) | FE-001 |
| FE-070 | P0 | 2d | Accessibility hardening pass and removal of suppressions | FE-010, FE-020, FE-030, FE-040, FE-045 |
| FE-080 | P0 | 2d | Frontend test harness (Playwright smoke + visual theme checks) | FE-001, FE-010 |
| FE-090 | P1 | 1d | Performance pass (bundle split + lazy loading + render tuning) | FE-005, FE-040, FE-045 |
| FE-100 | P0 | 1d | Release checklist, rollout validation, post-release fixes | FE-070, FE-080, FE-090 |

---

## FE-001 - Theme Runtime, Persistence, No-Flash Boot
Priority: P0
Estimate: 2 days

### Scope
- Add a centralized theme store with `light | dark | system`.
- Apply theme class before app hydration to avoid flash.
- Persist user preference in local storage.
- Add dynamic `meta[name="theme-color"]` updates per mode.

### Target Files
- `ghostwriter/frontend/src/lib/stores/theme.ts` (new)
- `ghostwriter/frontend/src/routes/+layout.svelte`
- `ghostwriter/frontend/src/app.html`
- `ghostwriter/frontend/src/lib/components/layout/AppShell.svelte`

### Acceptance Criteria
- Selecting theme updates UI immediately and persists after reload.
- `system` tracks OS preference changes.
- No first-paint light/dark flash on reload.
- Browser toolbar color updates for light and dark mode.

### Validation
- Manual: toggle modes, reload, switch OS theme.
- Run: `npm run check && npm run build`.

---

## FE-002 - Semantic Status Tokens and Color Cleanup
Priority: P0
Estimate: 1.5 days
Depends on: FE-001

### Scope
- Introduce semantic tokens (`--success`, `--warning`, `--info`, surfaces and foreground pairs).
- Replace hardcoded `green/amber/...` classes in route pages.
- Standardize success/warning/error cards and badges.

### Target Files
- `ghostwriter/frontend/src/routes/layout.css`
- `ghostwriter/frontend/src/routes/+page.svelte`
- `ghostwriter/frontend/src/routes/newsletters/+page.svelte`
- `ghostwriter/frontend/src/routes/settings/+page.svelte`
- `ghostwriter/frontend/src/lib/components/ui/badge/badge.svelte` (if needed)

### Acceptance Criteria
- No hardcoded status color classes remain in route surfaces.
- Status components have equivalent contrast in light and dark themes.

### Validation
- Contrast spot checks on all status banners/cards.
- Run: `npm run check && npm run build`.

---

## FE-003 - Shared Utility Extraction
Priority: P1
Estimate: 1 day

### Scope
- Extract repeated date parsing/formatting logic into shared utilities.
- Extract shared digest download helper.
- Extract status badge variant mapping to common utility.

### Target Files
- `ghostwriter/frontend/src/lib/utils/date.ts` (new)
- `ghostwriter/frontend/src/lib/utils/digest.ts` (new)
- `ghostwriter/frontend/src/routes/+page.svelte`
- `ghostwriter/frontend/src/routes/digests/+page.svelte`
- `ghostwriter/frontend/src/routes/feeds/+page.svelte`
- `ghostwriter/frontend/src/routes/settings/+page.svelte`

### Acceptance Criteria
- No duplicated `parseUTC` helper in route files.
- Shared helpers are used by all relevant pages.

### Validation
- Run: `npm run check && npm run build`.

---

## FE-004 - Remove Debug Logs and Improve Auth State UX
Priority: P1
Estimate: 1 day

### Scope
- Remove `console.log` debug traces from auth and layout paths.
- Ensure auth failures show user-friendly, actionable messages.
- Keep auth initialization resilient without noisy logs.

### Target Files
- `ghostwriter/frontend/src/lib/stores/auth.ts`
- `ghostwriter/frontend/src/routes/+layout.svelte`
- `ghostwriter/frontend/src/lib/components/layout/LoginScreen.svelte`

### Acceptance Criteria
- No debug logs in production code paths.
- Login, expired session, and server-down states remain clear.

### Validation
- Manual auth flow test: valid login, invalid login, expired token.
- Run: `npm run check && npm run build`.

---

## FE-005 - Componentization Scaffold for Oversized Routes
Priority: P0
Estimate: 2 days
Depends on: FE-003

### Scope
- Split large route files into feature components and page containers.
- Create per-route component folders.
- Keep route files mostly orchestration + data hooks.

### Target Files
- `ghostwriter/frontend/src/routes/settings/+page.svelte`
- `ghostwriter/frontend/src/routes/feeds/+page.svelte`
- `ghostwriter/frontend/src/routes/digests/+page.svelte`
- `ghostwriter/frontend/src/routes/+page.svelte`
- `ghostwriter/frontend/src/lib/components/features/*` (new)

### Acceptance Criteria
- No route file exceeds 500 lines.
- Shared UI logic moved into reusable components.

### Validation
- Run: `npm run check && npm run build`.
- Manual regression pass across all routes.

---

## FE-006 - Frontend README and Contributor Guide
Priority: P1
Estimate: 0.5 day

### Scope
- Replace template README with project-specific frontend docs.
- Add local dev, checks, structure, and UX conventions.

### Target Files
- `ghostwriter/frontend/README.md`

### Acceptance Criteria
- README contains clear setup, architecture overview, and QA checklist.

---

## FE-010 - Settings IA Split
Priority: P0
Estimate: 3 days
Depends on: FE-005

### Scope
- Break settings into logical sub-sections or nested routes:
  - General
  - Scheduling
  - Integrations
  - Security (tokens/session)
  - Logs
- Keep destructive actions isolated and clearly labeled.

### Target Files
- `ghostwriter/frontend/src/routes/settings/+page.svelte` and/or nested route files
- `ghostwriter/frontend/src/lib/components/features/settings/*`

### Acceptance Criteria
- Users can find any settings task in <=2 navigation decisions.
- Long scroll is removed from default settings view.

### Validation
- Manual usability pass with five tasks:
  - change schedule
  - create token
  - configure wallabag
  - set transcription provider
  - download logs

---

## FE-020 - Dashboard Workflow Redesign
Priority: P1
Estimate: 2 days
Depends on: FE-005

### Scope
- Move key actions and alerts above secondary stats.
- Clarify current digest pipeline state and next scheduled run.
- Improve empty/error states with direct CTA.

### Target Files
- `ghostwriter/frontend/src/routes/+page.svelte`
- `ghostwriter/frontend/src/lib/components/features/dashboard/*`

### Acceptance Criteria
- Triggering digest and locating current status are both first-screen actions.
- Critical states (offline, processing, failure) have distinct visual hierarchy.

---

## FE-030 - Feeds UX Overhaul
Priority: P1
Estimate: 2.5 days
Depends on: FE-005

### Scope
- Add better filtering (status/mode) and count summaries.
- Add optional bulk actions (enable/disable/delete selected).
- Improve add/edit forms with stronger validation and defaults.
- Improve mobile card actions parity with desktop.

### Target Files
- `ghostwriter/frontend/src/routes/feeds/+page.svelte`
- `ghostwriter/frontend/src/lib/components/features/feeds/*`

### Acceptance Criteria
- Bulk updates work with optimistic feedback and clear confirmations.
- Form validation errors are explicit before submission.

---

## FE-040 - Digests UX Overhaul
Priority: P1
Estimate: 2 days
Depends on: FE-005

### Scope
- Add filters (status/period/date range) and sort controls.
- Add pagination or load-more for long history.
- Improve action discoverability (read/download/delete).

### Target Files
- `ghostwriter/frontend/src/routes/digests/+page.svelte`
- `ghostwriter/frontend/src/lib/components/features/digests/*`

### Acceptance Criteria
- Users can find a digest from last month quickly without manual scrolling.
- Actions remain accessible on mobile and desktop.

---

## FE-045 - Reader Experience Upgrade
Priority: P1
Estimate: 2 days
Depends on: FE-001, FE-005

### Scope
- Add reader controls: text size, reading width, line height.
- Persist reader preferences locally.
- Ensure dark-mode typography support (`prose` strategy).
- Improve keyboard navigation for article switching and TOC.

### Target Files
- `ghostwriter/frontend/src/routes/digests/[id]/read/+page.svelte`
- `ghostwriter/frontend/src/lib/components/features/reader/*`

### Acceptance Criteria
- Reader content remains readable and high-contrast in dark mode.
- Keyboard-only navigation supports previous/next and TOC selection.

---

## FE-050 - Newsletters UX Refresh
Priority: P2
Estimate: 1 day
Depends on: FE-002

### Scope
- Improve OAuth flow messaging and reconnect states.
- Clarify setup guidance and troubleshooting.

### Target Files
- `ghostwriter/frontend/src/routes/newsletters/+page.svelte`

### Acceptance Criteria
- Connected/disconnected/not-configured states are visually and textually unambiguous.

---

## FE-060 - App Shell and Navigation Improvements
Priority: P2
Estimate: 1 day
Depends on: FE-001

### Scope
- Add theme toggle in desktop and mobile shell.
- Improve active nav affordance and context cues.
- Optional: add quick action entry point for “Generate Digest”.

### Target Files
- `ghostwriter/frontend/src/lib/components/layout/AppShell.svelte`
- `ghostwriter/frontend/src/lib/components/layout/*`

### Acceptance Criteria
- Theme toggle is always reachable within one click/tap.
- Current section is clear on all breakpoints.

---

## FE-070 - Accessibility Hardening
Priority: P0
Estimate: 2 days
Depends on: FE-010, FE-020, FE-030, FE-040, FE-045

### Scope
- Remove `svelte-ignore` a11y suppressions and fix root causes.
- Verify dialog/sheet focus trapping and escape behavior.
- Confirm labels, role semantics, and keyboard activation on controls.

### Target Files
- All touched route/components from M2

### Acceptance Criteria
- No a11y suppression comments remain in app routes.
- Keyboard-only task completion for core flows is possible.

---

## FE-080 - Test Harness: Smoke + Theme Visual Checks
Priority: P0
Estimate: 2 days
Depends on: FE-001, FE-010

### Scope
- Add Playwright test setup for key journeys.
- Add light/dark screenshot snapshots for critical pages.
- Cover auth gate + dashboard + feeds + digests + settings navigation.

### Target Files
- `ghostwriter/frontend/playwright.config.ts` (new)
- `ghostwriter/frontend/tests/e2e/*` (new)
- `ghostwriter/frontend/package.json` scripts

### Acceptance Criteria
- CI/local can run a minimal e2e suite.
- Theme regressions are caught by snapshots.

---

## FE-090 - Performance Pass
Priority: P1
Estimate: 1 day
Depends on: FE-005, FE-040, FE-045

### Scope
- Lazy-load heavy reader logic (Readability/DOMPurify path only when needed).
- Audit and reduce large route chunks where possible.
- Optimize repeated query refetch behavior and unnecessary rerenders.

### Acceptance Criteria
- Largest route bundles are reduced from baseline after refactor.
- No UX regression in loading or interactivity.

### Validation
- Compare `npm run build` chunk output before/after.

---

## FE-100 - Release and Rollout
Priority: P0
Estimate: 1 day
Depends on: FE-070, FE-080, FE-090

### Scope
- Execute final QA matrix for light/dark + desktop/mobile.
- Update docs and release notes.
- Track post-release defects and apply fast-follow patch list.

### Acceptance Criteria
- All P0/P1 tickets closed or explicitly deferred with rationale.
- Release checklist signed off.

---

## Suggested Sprint Breakdown
- Sprint 1: FE-001, FE-002, FE-003, FE-004, FE-006
- Sprint 2: FE-005, FE-010
- Sprint 3: FE-020, FE-030, FE-040
- Sprint 4: FE-045, FE-050, FE-060
- Sprint 5: FE-070, FE-080, FE-090, FE-100

## Execution Notes
- Start with FE-001 and FE-002 before visual redesign work.
- Avoid touching backend API contracts unless a ticket explicitly requires it.
- Keep each PR scoped to one ticket when possible.
