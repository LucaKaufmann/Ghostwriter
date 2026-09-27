# Web / integrations / operations autonomous work packages

Prepared 2026-09-27 against audit/current source at `cdb776d`. Read-only source validation; no tests rerun, credentials loaded, app changes, network calls, or deployment. The package IDs below are stable; root owns their dispatch and dependency ledger.

All packages inherit the [master backlog](backlog.md) and [worker launch prompt](worker-prompt.md).

## Global execution contract

Each package gets its own branch/worktree from the orchestrator-selected integration SHA. Do not edit shared task notes, `docs/project-state.md`, audit documents, schema/contracts, generated artifacts, or another package's files. Return changes, exact commands/results, limitations, branch/worktree/commit, PR URL, and next action. Stop and report an interface change before expanding ownership. The orchestrator reviews and verifies integrated output. Opening PRs when launched is authorized by the user; merging, release tags, published artifacts, deployment, production accounts/content, and paid providers are outside these packages. Missing runtimes/network permissions are verification blockers, never a pass. Use only synthetic data and isolated storage.

## KO-01

**Preserve unrelated books and repair manual connection settings**

**PR:** `fix: protect KOReader downloads and connection settings`

**Outcome / rationale:** retention only deletes artifacts provably created by this plugin; save/cancel uses the actual manual connection dialog. Source reconfirmed: `ghostwriter_sync.lua` currently enumerates all EPUBs; `main.lua` declares `dialog` inside its initializer.

**Ownership:** `ghostwriter/koreader/ghostwriter.koplugin/ghostwriter_sync.lua`, `ghostwriter_settings.lua`, `main.lua`; new Lua test harness under `ghostwriter/koreader/tests/`; plugin README. Touch `ghostwriter_api.lua` only for filename/path validation if needed. No backend ZIP exporter or auth-token changes.

**Design constraint:** use durable plugin-owned download records scoped to server + download-directory identity, or an equally explicit ownership scheme. Never infer ownership from every existing EPUB or a broad filename prefix. Pre-existing files and filename collisions are not automatically adopted. Absent/corrupt ownership state must fail safe by retaining files. Validate containment before writes/deletes, including `..`, absolute paths, symlinks, and malformed ownership entries. Mark ownership only after successful `.part` finalization. Do not advance a cursor past unsuccessful download/durable bookkeeping. Preserve existing sync-on-suspend settings and zero-retention meaning. Local-first cleanup is a data-integrity change deserving independent review.

**Acceptance:** mixed library preserves unrelated books byte-for-byte; only owned overflow removed; missing/corrupt manifest deletes nothing; switching directory/server cannot make old records apply to new files; interrupted/failed downloads and settings-save failure preserve retry eligibility; no deletion outside destination; repeat sync and existing-file collision are safe; retention zero disables deletion; save/cancel invoke the current dialog and save intended values. Existing successful contiguous-cursor behavior remains covered.

**Checks:** add standalone mocked-KOReader harness with explicit run command, suggested `lua ghostwriter/koreader/tests/run.lua`; use sandbox temporary directories and stub network/UI. Lua/LuaJIT not on this host's PATH during planning. Provision a user/local or CI runtime before acceptance; device behavior is still unverified without KOReader hardware. A host Lua mock test is not a device validation.

**Dependencies / conflicts:** independent of backend retention (different owners). One owner for all plugin files. No API contract change required. CI owner may later invoke harness; this package does not edit shared workflows.

## HELPER-01

**Keep bearer credentials within configured transport origin**

**PR:** `fix: bind podcast helper credentials to the configured origin`

**Outcome / rationale:** neither server-supplied audio URLs nor redirects can send the Ghostwriter token to another origin. Reconfirmed `request_json`, `request_bytes`, and `download_episode` use default urllib opening and unrestricted absolute audio URLs.

**Ownership:** `skills/ghostwriter-one-off-podcast/scripts/create_one_off_podcast.py`, new `skills/ghostwriter-one-off-podcast/tests/test_transport.py`, focused transport documentation in that skill's README/SKILL.md only if necessary. No provider/model guidance rewrites or backend API changes.

**Confirmed default:** reject authenticated cross-origin downloads/redirects rather than silently adding CDN trust. Origin compares scheme + normalized hostname + effective port. Permit existing intentional same-origin loopback HTTP and explicit non-loopback `--allow-insecure-http`; that flag is not permission to redirect from HTTPS to HTTP. Validate every redirect hop for JSON submission/polling and audio download. Reject URL userinfo, unsupported schemes, malformed ports, and downgrade; handle scheme-relative, relative, and absolute locations explicitly. Preserve bounded redirect behavior and CLI exit-code contracts.

**Acceptance:** approved same-origin requests work; default-port equivalence works; different hostname/port/scheme are denied before credentials are sent; same-origin multi-hop redirect works; cross-origin hop after same-origin hop is denied; HTTPS downgrade denied even with insecure flag; loop/too-many redirects fails; synthetic token never appears in errors/artifacts. Preserve JSON handling, timeout, preview, private-manifest permissions, no automatic env loading for preview, and download failure exit category. Test POST redirect method/body behavior so a fix does not accidentally resend source material.

**Checks:** `python3 -m unittest discover -s skills/ghostwriter-one-off-podcast/tests -p 'test_*.py'`; compile/help/preview using synthetic input. Tests must exercise the installed custom redirect handler/opening path (mocking only the top-level URL opener would miss this defect); fake handler responses or loopback fixture with outbound denied. No real URL fetch, LLM/TTS, personal `~/.env`, or token.

**Dependencies / conflicts:** fully independent; CI owner adds appropriate skill path trigger and invocation later. No full-repository release required to review this fix. Security review required before ready PR.

## WEB-01

**Make browser navigation evidence runnable in CI**

**PR:** `test: run current Ghostwriter browser smoke flows in CI`

**Outcome / rationale:** repair confirmed `/feeds` expectations versus `/sources/feeds`, then run browser assertions on Linux. Audit browser runtime was blocked before assertions by missing Chromium; static mismatch is the current evidence.

**Ownership:** `ghostwriter/frontend/tests/e2e/navigation-theme.spec.ts`, `auth-gate.spec.ts`, `fixtures/mockApi.ts`, new smoke specs, `playwright.config.ts`, browser test docs in frontend README, and a new `.github/workflows/ghostwriter-browser.yml`. Existing shared PR workflow remains owned by the backend/CI package. Package/lockfile only if an actual needed dependency change is approved by orchestrator; Playwright already exists.

**Acceptance:** current sidebar navigation and legacy `/feeds` redirect tested independently; auth gate/login success and rejection covered; deterministic authenticated route smoke covers dashboard, source feeds, digests, settings, and episodes where existing fixtures support them. Mock only known API endpoints and fail unexpected network calls so mock catch-all responses cannot hide contract drift. No live backend/provider required. Install exact lockfile browser in Linux CI; upload traces/screenshots on failure. Separate portable behavioral checks from platform visual baselines. Keep and deliberately review visual coverage (e.g. dedicated Linux snapshot project), never blindly update images just to silence failures or silently skip all snapshots. Real rendered screenshots must be inspected.

**Checks:** from frontend, `npm ci`, `npm run check`, `npm run build`, `npx playwright install --with-deps chromium` (CI Linux), `npm run test:e2e` or documented behavior/visual projects. Chromium missing locally may need dependency download approval; Node audit version was 24.21.0. Pin CI Node major 24 as existing PR checks. Explicitly label fixture-backed browser coverage; it is not frontend/backend end-to-end generation proof.

**Dependencies / conflicts:** independent if new workflow. It owns common mock fixtures and existing auth spec; WEB-02 runs after this merges. Coordinate workflow paths with CI owner so no duplicate execution or omission. Do not replace current sidebar routes/UI to accommodate stale tests.

## WEB-02

**Handle expired sessions by HTTP status**

**PR:** `fix: handle expired web sessions without retrying unauthorized requests`

**Outcome / rationale:** query retry currently searches error text for `401`, while `ApiError.status` holds the actual status. Define recovered sign-in flow after in-session 401 without treating unrelated server failures as logout.

**Ownership:** `ghostwriter/frontend/src/routes/+layout.svelte`, `src/lib/api/client.ts`, `src/lib/stores/auth.ts`, new `tests/e2e/session-expiry.spec.ts`; shared mock fixture only after WEB-01. No backend auth changes or unrelated feature pages.

**Acceptance:** 401 with message lacking digits is not retried; valid authenticated data request returning 401 clears that session and presents sign-in, clears/cancels old user cache/pollers, and permits fresh login. 403 permission denial is classified without automatically assuming session expiry; 5xx/network errors preserve credentials and bounded retries. Failed login remains correct. Concurrent responses from old token must not invalidate a newly logged-in session. Avoid circular API/store dependencies and duplicate global event handlers. Verify request and download error handling, not only query happy paths.

**Checks:** frontend check/build plus fixture browser tests with measured request counts, concurrent/delayed 401, successful re-login, forbidden response and transient error. No production session. Run after WEB-01 browser harness works. Independent review useful due auth-state behavior.

**Dependencies / conflicts:** after WEB-01; backend AUTH work can run independently since no endpoint/schema contract changes. Don't conflate `ApiError.isUnauthorized` (currently 401 or 403) with invalid authentication; document actual status policy.

## DEPLOY-01

**Document deployment portability gap; hold personal script repair**

**Status:** not ready as an autonomous PR implementation task. `git ls-files ghostwriter/deploy.sh` is empty; `git check-ignore -v ghostwriter/deploy.sh` identifies `ghostwriter/.gitignore:64:deploy.sh`. This is an ignored personal script, not portable repository source. Never force-add it or reproduce its personal host/user/key defaults in a PR.

**Confirmed finding:** local source reads `SYNOLOGY_DIR` but executes Compose from `~`, then removes the container before validating Compose config. A local script fix would not produce the reviewable tracked PR outcome requested. Do not silently convert personal infrastructure into supported generic deployment.

**Safely actionable now:** RELEASE-01 should document that `deploy.sh` is a local, ignored convention, and that portable checkout validation must use explicit synthetic Docker/Compose commands. No ignored script mutation or deployment is needed to do that.

**Future bounded package if generic tooling is selected:** create a *new* tracked sanitized Synology deployment helper requiring explicit host/port/directory/image arguments, plus fake-transport tests under a new tools test directory. No personal defaults, credential files, or live transport; safe quoting for directory spaces/quotes; directory/file/config preflight before destructive actions; v2/fallback behavior; fail on image/config mismatch. Required checks: shell syntax and an executed remote-shell fixture with PATH stubs that hard-block real docker/ssh. User selection of maintaining generic deployment tooling is needed before widening scope this way. Actual deployment always requires separate authorization.

## RELEASE-01

**Prove synthetic migration/recovery readiness and document release gaps**

**PR:** `test: add a disposable Ghostwriter release readiness check`

**Outcome / rationale:** current 1.1.0 notes correctly describe schema 021, while HEAD reaches later revisions; clean container/pull/recovery were never established. Add a repeatable local synthetic readiness protocol and preserve historic release notes.

**Ownership:** new `ghostwriter/docs/release-readiness.md`, focused checklist amendments in `ghostwriter/RELEASE.md` only, new `ghostwriter/tests/test_release_recovery.py`. Reuse existing Alembic fixtures via imports where sensible; do not edit migration files or existing shared test fixtures without coordinating backend owner. No version bump, release announcement, tag, publish workflow change, production backup, image push/pull-access policy change, or deployment.

**Acceptance:** disposable database/files verify fresh `alembic upgrade head` and upgrade from last released revision 021 with synthetic representative rows/artifacts preserved; snapshot all documented persistent volumes before upgrade, demonstrate restore into a new directory and usable data; run current head twice to establish idempotent startup. Invalid migration/startup is surfaced, never silently start unsupported schema. Document precise single-process scheduler/runtime assumption after checking source; inventory HEAD changes as unreleased, not a fabricated new release. Separate local CI evidence from pending physical device/provider/registry acceptance. Registry public/private pull intent and exact release scope remain user decisions.

**Checks:** targeted pytest readiness test plus `tests/test_alembic_bootstrap.py` and `tests/test_podcast_multi_digest_migration.py`, activated venv (Alembic subprocess lookup), no `.env`, temp `DATA_DIR`/`OUTPUT_DIR`/`LOGS_DIR`, outbound blocked. Optional locally built container health/migration restart smoke with unique names/volumes, no production mounts. Docker CLI exists here; daemon availability unverified. Fresh apt/build deps require network; report blocked separately. Local fixture audio/files can prove artifact preservation, not provider/audio-quality validation.

**Dependencies / conflicts:** execute final evidence after dependency and relevant data-integrity packages merge. Keep RELEASE-01 own docs to avoid README overlap. Backend cleanup/migration owner must approve fixture invariants and any migration failure fix; report discovered unrelated defects rather than unbounded repair. Future pinned GHCR image pull is read-only and can be separately scheduled once intended release/access target is known; publishing/deployment needs explicit later authorization.

## Dispatch

Use the master [backlog](backlog.md) for sequence and ownership. Python dependency parity belongs only to ENV-01; Docker source/runtime pinning belongs only to RUNTIME-01. DEPLOY-01 below is a held local infrastructure finding, not a public PR assignment. Product positioning, new UIs, and provider quality remain separate decisions.
