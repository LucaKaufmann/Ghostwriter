# Ghostwriter web, e-reader, helper, and operations audit

Audit date: 2026-09-27. Read-only source review; no application source, configuration, credentials, or deployment modified. All relative paths below are relative to `/Users/luca/git/Epilogue`.

## Product understanding

The repository has grown beyond its original RSS-to-EPUB focus into a personal, self-hosted reading and listening service. Ghostwriter is the backend and web control plane; Epilogue remains the mobile client name. The user subscribes to RSS, Gmail newsletters, saved Wallabag items, podcast feeds, and YouTube channels. The server extracts or transcribes source material, optionally summarizes it, packages EPUB/PDF digests, and can create narrated single-host or two-host podcast episodes. Delivery surfaces are web reading, file download, mobile synchronization, private podcast RSS, and KOReader incremental EPUB download. An independent agent skill also turns local notes/documents/URLs into ad hoc episodes.

This is implemented software with substantial breadth, not a blank prototype. The web frontend is a Svelte 5/TypeScript SPA using SvelteKit static adapter, Tailwind 4, Bits UI component wrappers, TanStack Query, DOMPurify, Readability, and a single `/api` client. FastAPI serves the static output in production; Vite proxies API calls for development. The main information architecture has recently consolidated sources under `/sources/*` and generated content under `/digests` and `/episodes`; old URLs retain redirects and some older duplicate page implementations.

## Implemented web flows

- **Authentication and first run:** check public health and setup status, register the first admin or sign in, persist a bearer token in localStorage, verify via `/auth/me`, fail closed on verification errors. Legacy token-login support remains in the auth store. UI shell renders only after successful auth. Evidence: `frontend/src/lib/stores/auth.ts`, `frontend/src/lib/components/layout/LoginScreen.svelte`, `frontend/src/routes/+layout.svelte` (all beneath `ghostwriter/`).
- **Dashboard:** server health/provider, active feed count, recent and weekly digest summaries, next schedule, latest run, media-processing progress; manual generation and EPUB/PDF downloads. `ghostwriter/frontend/src/routes/+page.svelte:28` onward.
- **Feeds:** add/edit/delete/toggle RSS feeds, raw vs summary mode and article cap, search/filter/sort, selections and bulk activation/deletion, clear seen articles, URL checking. `ghostwriter/frontend/src/lib/components/features/feeds/FeedsPage.svelte`.
- **Media Sources:** unified tabs for podcast feeds and YouTube channels, URL/channel resolution, enable/edit/delete, processed item lists, recent processing runs, individual/bulk failed-item retry, transcript and summary detail pages. `ghostwriter/frontend/src/lib/components/features/media/MediaPage.svelte:43` onward and `src/routes/sources/media/items/[id]/+page.svelte`.
- **Newsletters:** Gmail readiness/connected state, OAuth popup, refresh on window focus, setup/troubleshooting text; integration controls and previews also live in Settings. `ghostwriter/frontend/src/routes/sources/newsletters/+page.svelte:25` onward. OAuth intentionally does not use bearer authentication on its browser redirect entry point; backend authorization scope merits separate review.
- **Digests:** generation, filters and pagination, status, cover loading, deletion, EPUB/PDF output, open web reader, create/listen to generated podcast. `ghostwriter/frontend/src/lib/components/features/digests/DigestsPage.svelte`.
- **Reader:** table of contents, previous/next and keyboard navigation, local typography preferences, server-fetched source HTML processed with Readability, fallback digest HTML, DOMPurify sanitation and safe external anchor attributes. Media content avoids original-source extraction. `ghostwriter/frontend/src/lib/components/features/reader/ReaderPage.svelte:61`, `:91`, `:266`.
- **Episodes:** list/filter/sort existing episodes, manually trigger the scheduled-generation path, progress polling, retry/delete/download; detail page has audio player, transcript grouped by speaker/section, source articles, cost/duration metadata. `ghostwriter/frontend/src/lib/components/features/episodes/EpisodesPage.svelte:38` and `src/routes/episodes/[id]/+page.svelte`.
- **Settings:** General / Schedule / Integrations / Security / Logs tabs. Provider/model summary is read-only environmental configuration. Configurable PDF format, AI/manual covers, digest schedules, podcast schedules, provider/voice/host/style/length/script settings, podcast feed base URL and artwork, Wallabag credentials/test/preview/reset, Gmail, Whisper model download/activation/delete/provider/timeout, API token creation/revocation, token-embedded KOReader ZIP, log downloads. `ghostwriter/frontend/src/lib/components/features/settings/SettingsPage.svelte:1059` onward.
- **Important feature boundary:** no one-off episode creation UI/API-client method appears under frontend source. One-off document/notes input exists in the Python helper and backend, whereas Episodes UI generates from scheduled/current digest inputs. Distinguish input media podcasts from output generated podcast episodes in future product language.

## KOReader implementation

Plugin menus configure URL/token/download directory/retention and optionally sync on suspend/poweroff/reboot. Calls `/api/digests/new?last_known_id=...`, sorts oldest first, uses Authorization headers, downloads through `.part` and rename, skips existing files, advances the cursor only through contiguous successes, and prunes older EPUBs. The web download endpoint mints an API token and embeds defaults in `ghostwriter_settings.lua`. The plugin README explicitly calls it an MVP scaffold requiring hardware validation. No Lua/device tests were found.

## Distributable helper

`skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py` is a 1,476-line standalone standard-library CLI. It supports URL/text-file/JSON sources, Obsidian note/folder selection, tags/globs, linked-note depth/backlinks, Markdown cleanup, source splitting, source hashing/manifest, redacted preview, private saved JSON, research guidance, provider/voice generation overrides, polling, MP3 download, and explicit exit codes. It reads only `~/.env` automatically for actual submissions, permits explicit env files, and rejects non-loopback HTTP by default. Preview exits before loading environment files. There are backend one-off API tests, but no discovered tests exercising this helper itself. The skill text contains extensive provider model/voice assertions; those are documented claims, not independently verified live provider capabilities in this audit.

## Operational and release posture

- Container has frontend/Python/Whisper multi-stage build, non-root runtime, ffmpeg/PDF dependencies, Alembic-before-Uvicorn startup, health probe, OCI labels. Compose persists separate data/output/log volumes, default GHCR latest image, optional Ollama sidecar; dev override builds local source.
- GitHub PR workflows run eight backend smoke-test modules, frontend typecheck/build, and amd64 container build plus `/health` smoke. Release tags publish amd64+arm64 images with version/major/minor/latest/SHA tags, provenance and SBOM. Good baseline, but no frontend browser suite or mobile checks appears in these workflows.
- Release checklist includes targeted testing, fresh DB migration, pinned image verification, backups, logs/login/config/feed checks. Release 1.1.0 notes explicitly record an unresolved public GHCR pull visibility issue. This is a historical limitation in the repository, not proof the registry is still inaccessible today.
- `deploy.sh` represents personal Pi/Synology/Mac deployment conventions, with external compose paths and private host/key defaults. It is not a generic deployment interface and should never be run automatically merely to audit or validate code.

## Prioritized concrete findings

### P1 — KOReader retention can delete unrelated books

`ghostwriter/koreader/ghostwriter.koplugin/ghostwriter_sync.lua:35-68` enumerates **every `.epub`** in the selected download directory and deletes everything beyond the newest N by modification time. It keeps no managed-file manifest or Ghostwriter filename ownership check. Retention defaults to 30 (`ghostwriter_settings.lua:19`), while the UI permits choosing an arbitrary folder (`main.lua:143-150`). Selecting an existing books folder therefore puts unrelated EPUBs at risk after a sync returning digests. Fix should scope deletion to recorded managed downloads or a dedicated owned subdirectory, and test mixed-content folders. Static confirmed logic; no books were touched.

### P1 — Helper bearer token is forwarded across URL origins and redirects

`skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py:1132-1156` trusts an absolute `download_url`/`stream_url` from episode detail. `:272-289` adds the Ghostwriter Authorization bearer header to that arbitrary URL. `:232-257` and `:272-289` use default `urllib.request.urlopen`, whose redirect handler retains Authorization on cross-origin redirects. The initial HTTPS guard is not a same-origin or per-redirect guard. Reproduced safely with synthetic token and mocked `urlopen`: configured origin `https://configured.example/api`, returned `https://different.example/audio`, and the different origin received the synthetic bearer header. Separately constructing the stdlib redirect request retained Authorization for a different HTTPS host. No real credentials or network were involved. Constrain authenticated requests/downloads to expected origin, and validate redirects/strip credentials (including HTTPS downgrade checks) at each hop.

### P2 — KOReader manual connection dialog references an out-of-scope local

`ghostwriter/koreader/ghostwriter.koplugin/main.lua:102` declares `local dialog = MultiInputDialog:new({...})`; initializer callbacks at `:121-131` refer to `dialog`. In Lua, the new local is not in scope inside its initializer, so these closures resolve an outer/global `dialog`. Save calls `dialog:getFields()` and can fail; Cancel passes the wrong/nil dialog. Declare the local first, assign in the next statement. Static language-semantics finding; Lua and actual KOReader hardware were unavailable, so no runtime reproduction claimed.

### P2 — Browser navigation tests are stale and are not run by CI

`ghostwriter/frontend/tests/e2e/navigation-theme.spec.ts:12,28,41` assumes a sidebar link to `/feeds`. Real AppShell now links `/sources/feeds` (`src/lib/components/layout/AppShell.svelte:37`); `/feeds/+page.ts:4` redirects. Both navigation and multi-route screenshot flows therefore contain deterministic locator/assertion mismatches. CI ends at `npm run build` (`.github/workflows/ghostwriter-pr-check.yml:63-91`) and never executes these tests. Snapshots are Darwin-specific, while CI is Linux. Browser suite also covers only login/navigation/theme, not generation, downloads, token flows, media or episode behavior. Actual assertion execution could not be completed: first sandbox loopback blocked; after allowed loopback escalation, installed Playwright lacks the required Chromium executable. Do not report this as a runtime-confirmed navigation failure; it is a confirmed source mismatch with infrastructure-blocked execution.

### P2 — Release builds are not reproducible from commit alone

`ghostwriter/Dockerfile:50` clones whisper.cpp default-branch HEAD and `:100` installs unpinned yt-dlp. Floating base images/dependency ranges add drift. The same commit/tag rebuilt later can use different media binaries and incompatible APIs. `ghostwriter/RELEASE.md:122` already acknowledges yt-dlp. Pin validated upstream versions/commits with a controlled update process, especially given ARM transcription compatibility concerns documented in README.

### P2 — CI and runtime language versions differ

Container uses Node 22 and Python 3.11 (`ghostwriter/Dockerfile:5,19,62`); PR checks use Node 24/Python 3.12 (`.github/workflows/ghostwriter-pr-check.yml:30,77`). Container smoke checks startup only, not the backend test selection on Python 3.11. No actual incompatibility demonstrated, but passing CI does not establish supported-runtime behavior. Align versions or explicitly test the intended version matrix.

### P2 — Synology deployment ignores its configured remote directory

`ghostwriter/deploy.sh:13` reads `SYNOLOGY_DIR` into `REMOTE_DIR`, but remote command changes to `~` at `:29` and invokes Compose without `-f` at `:40`. It may use a different compose file or fail after deleting the container. Existing personal home-directory deployment may happen to match this behavior; the advertised directory override cannot work as written. In addition, the script loads `ghostwriter:latest` while the checked-in generic Compose uses GHCR by default; external compose files are an unverified prerequisite. No deployment was run.

### P3 — Auth retry behavior disagrees with API error representation

`ghostwriter/frontend/src/routes/+layout.svelte:28-33` avoids retry only when `error.message` contains `401`. `ApiError` sets message to server detail, with HTTP status stored separately (`src/lib/api/client.ts:807-818`). Normal unauthorized messages need not include `401`, so expired-session queries are retried instead of being classified correctly. The API client also does not centrally transition an already-open UI to signed-out state on session expiry. Use typed status handling and test session expiration. No production auth session tested.

### P3 — Maintenance and documentation lag product scope

SettingsPage is 2,913 lines; MediaPage 1,396; API client ~830; helper 1,476. Older redirected media pages remain implemented, increasing duplicate-maintenance risk. Frontend README is still Svelte starter instructions. Main backend README's feature/API inventory under-represents podcasts, PDF, covers, and newer routes, and says all config is environmental despite persisted UI settings. Root product headline and naming need an explicit decision: retain RSS reading as core with audio extension, or position as a broader personal information-to-reading/listening product. These are prioritization questions, not evidence that a rewrite is required.

## Verification performed

- `npm run check` with existing dependencies and Node v24.21.0: **PASS, 0 errors / 0 warnings**. Log `/tmp/epilogue-web-check.log`.
- `npm run build`: **PASS**, static output produced. Only upstream unused-import warning observed (TanStack Query); log `/tmp/epilogue-web-build.log`.
- Existing Playwright `supports core route navigation` invocation: **BLOCKED BEFORE ASSERTIONS**, required Chromium headless-shell executable absent. Log `/tmp/epilogue-web-e2e.log`. Initial sandbox port restriction was overcome with allowed escalation; browser install not attempted.
- Helper synthetic offline preview: **PASS**, one source, stdout content redacted, manifest mode 0600. No env files loaded. Artifacts `/tmp/epilogue-helper-audit-preview.json`, `/tmp/epilogue-helper-audit-manifest.json`.
- Helper synthetic transport probes: **CONFIRMED** cross-origin absolute audio URL receives bearer and stdlib cross-origin redirect copies bearer. No actual network/credentials.
- No live provider generation, Gmail/Wallabag account actions, GHCR lookup/pull, deployment, or KOReader hardware validation performed. No helper unit suite exists to run.

## Recommended restart slice

First stabilize trust and evidence: protect KOReader managed files, repair dialog, bind helper credentials to allowed origins/redirects, restore browser test/tooling parity and add these regressions. Then establish one local end-to-end fixture flow: feed -> digest -> EPUB/PDF/web reader -> podcast -> private feed, with provider calls mocked. Separately confirm current published-image installation from a clean environment and record intended supported runtimes. Only after that choose the next product outcome (reading reliability, broader input capture, or one-off listening UX). Preserve existing product breadth; avoid an architectural rewrite before these concrete failure modes and product priorities are understood.
