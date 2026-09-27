# Backend PR work packages

Source recheck: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`, 2026-09-27. Read-only inspection confirms the affected code still matches the backend audit; no tests or runtime probes were rerun. Historical 243-pass/1-DNS-failure baseline remains historical evidence. No implementation is claimed here.

All packages inherit the [master backlog](backlog.md) and [worker launch prompt](worker-prompt.md).

## Rules shared by every assignment

- One isolated branch/worktree per PR, from the orchestrator's specified integrated base; return its absolute path, branch, commit SHA, PR URL, changed paths, executed commands/results, limitations and next action. Implementation-ready means a bounded assignment can start, not already verified.
- No edits outside the assigned paths, no shared planning-doc edits, no production data/.env, provider calls, deployment, merge, or unrelated refactor. Only the orchestrator allocates schema migration revisions. Prefer no schema changes in the early packages.
- Use disposable DB/output/log directories, disabled schedules, blank integrations, `.env` disabled before importing the application, and blocked outbound networking. Mock DNS deterministically without weakening the real URL validator. Once ENV-01 lands, use its checked-in hermetic fixture setup. Test failure/cancellation where acceptance requires it. Do not claim provider/audio end-to-end coverage.
- Existing APIs and public schemas remain compatible except documented error responses. All relevant checks must pass before a ready-for-review PR; if required verification is blocked, report it and keep any PR draft. Independent review is required for auth, outbound transport, retention and data-loss fixes. Rebase/retest against dependencies before acceptance.
- Commands below run from `ghostwriter/`, using a disposable environment installed from the repository's dependency declarations. Ruff checks cover changed Python files only; broad pre-existing lint cleanup is out of scope. Full backend suite is an integration check after independent PRs combine, rather than repeated for each cosmetic edit.

## AUTH-01

**P1: Auth throttling and deterministic session release (ready)**

Outcome: existing authentication enforces its configured request limit and does not leave connections checked out until GC.

Own existing `ghostwriter/app/api/auth.py`, `ghostwriter/app/core/security.py`, `ghostwriter/app/core/rate_limit.py`, `ghostwriter/tests/test_auth_registration.py`; new dedicated `ghostwriter/tests/test_auth_security.py` and `ghostwriter/tests/test_auth_rate_limit.py` allowed. Read `app/core/database.py`, `app/core/auth.py`, user/token models and config; do not change their schemas or shared conftest.

Confirmed: `security.py` still uses `next(get_session())`; limiter calls are unreachable after revocation return; login/register do not check it. Preserve first-registration SQLite lock and setup/JWT/API-token/legacy-key behavior; keep existing single-process, client-IP-based rate-limit contract, including configured disable. Do not add distributed throttling, proxy trust changes, new onboarding or tenant isolation.

Acceptance: threshold+1 returns 429 for public login/registration, appropriate valid/invalid requests consume the existing shared client bucket, independent client IPs are isolated, mocked time expiration permits recovery, disabled configuration remains disabled. Connection-pool checkout count returns to baseline without GC after setup, successful auth, missing/invalid credentials and query exceptions. Token revocation/last-used persistence and single-admin registration remain correct. Reset limiter state within local fixtures to prevent order dependence.

Verify: `python -m pytest -q tests/test_auth_registration.py tests/test_auth_security.py tests/test_auth_rate_limit.py tests/test_podcast_api.py`. The podcast file covers private-source ownership and authenticated endpoint compatibility. No dependency on another code package; consume ENV-01 once available.

## INGEST-01

**P1: Generate editions from any enabled source; honor Wallabag mode (ready with conservative contract)**

Own existing `ghostwriter/app/worker/bindery.py`, `ghostwriter/tests/test_bindery_seen_articles.py`, `ghostwriter/tests/test_bindery_filtering.py`; new `ghostwriter/tests/test_bindery_source_combinations.py`. Read Wallabag/newsletter/media services/models, do not mutate them, `app/api/digests.py`, or frontend/native contracts.

Confirmed: two early returns prevent Wallabag/newsletter-only and media-only editions; enrichment checks environment mode although Wallabag service already resolves DB configuration. Evaluate all enabled sources before declaring empty; derive mode from the same effective Wallabag service configuration. Default for this PR: preserve existing `completed` with zero articles for truly empty input and existing API shape; no new job enum/status or UX redesign. Log accurately that all eligible sources were considered. This preserves compatibility while leaving empty-edition product UX for an explicit later decision.

Acceptance matrix: no RSS + Wallabag; no RSS + Gmail; podcast transcript only; YouTube transcript only; active but empty RSS + media; all empty; disabled integration/inclusion flags; already seen/consumed material; filtered inputs. Eligible cases persist article rows and a readable nonempty EPUB. DB mode summarize/env raw and DB raw/env summarize follow DB; env fallback still works. Mocked LLM failure preserves current raw fallback. Failure before durable output does not mark sources/seen rows/media consumed; retry succeeds exactly once for that boundary. Do not expand into full distributed atomicity; record later-boundary gaps for RECOVERY-01.

Verify: `python -m pytest -q tests/test_bindery_source_combinations.py tests/test_bindery_seen_articles.py tests/test_bindery_filtering.py tests/test_digest_ordering_and_epub.py tests/test_bindery_digest_filenames.py tests/test_newsletter_service.py`. Independent implementation from AUTH-01/ENV-01; RECOVERY-01 implementation must follow INGEST-01 because it also owns bindery.

## ENV-01

**P1 enabling work: Reproducible backend installation and hermetic tests (ready)**

Own existing `ghostwriter/pyproject.toml`, `ghostwriter/requirements.txt`, `ghostwriter/tests/conftest.py`, and only DNS-fixture changes in `ghostwriter/tests/test_feeds.py`; new `ghostwriter/tests/test_dependency_metadata.py` if it exercises a real manifest invariant. Reserve a small `ghostwriter/README.md` setup/testing section with orchestrator; do not own global docs or CI workflows. Coordinate `test_feeds.py` with sync owner; fixture edit should precede their work.

Confirmed runtime metadata omits Alembic, bcrypt, python-jose, youtube-transcript-api, Mutagen (and declared requirements also include pytz). Conftest redirects storage but imports the app without disabling `.env` or blanking all external integration settings. Feed-sync unit test depends on actual DNS.

Outcome: one dependency source of truth (prefer pyproject runtime/dev dependencies; keep requirements as a compatible install entry point or mechanically verified export), clean project-metadata install imports app and collects all tests, and plain repository test command is deterministic/offline. Preserve declared compatible ranges; broad upgrades and lock-policy selection are out of scope. Do not install globally or read real `.env` to prove isolation. Fixtures must let transport-specific tests use mocks without disabling real URL safety logic.

Acceptance: disposable install by documented project path and compatibility requirements path; `pip check`; complete test suite with outbound connections/DNS blocked except explicit fixture DNS; synthetic sentinel `.env` proves no credentials/scheduler config enters tests; no writes outside disposable dirs. A clean environment must collect podcast tests without special `/tmp` package injections. Dependencies needing native libraries are documented, not silently skipped.

Verify: `python -m pip install -e '.[dev]'`; `python -m pip check`; `python -m pytest -q` in clean temp environment; separately `python -m pip install -r requirements.txt` in another temp environment followed by import/collection. Report unavailable package downloads/native prerequisites as blocked, not passes. CI owner can consume the standard command after this merges. Docker whisper.cpp/yt-dlp pinning is a separate follow-up if release scope needs reproducibility; do not silently select new versions here.

## FETCH-01

**P2/security: Bounded outbound fetching and intentional DNS failures (ready for scoped guard; DNS rebinding requires explicit proof)**

Own existing `ghostwriter/app/core/net.py`, `ghostwriter/app/services/content_processor.py`, `ghostwriter/app/services/reader_service.py`, `ghostwriter/tests/test_content_processor.py`, `ghostwriter/tests/test_reader_service.py`; new `ghostwriter/app/services/outbound_fetch.py` and `ghostwriter/tests/test_outbound_fetch.py` if useful. Read media/one-off callers to preserve contracts. No edits to `app/api/feeds.py` or `app/api/sync.py`; coordinate with INPUT-01/sync owner for API errors.

Confirmed RSS `feedparser.parse(URL)` and extraction `trafilatura.fetch_url(URL)` bypass application redirect revalidation. Shared URL validator lets `socket.gaierror` escape. Reader helper checks redirect URLs but does not pin DNS; it is not proof of complete rebinding protection.

Outcome: fetch bounded bytes through an explicit transport, validate each redirect target, then pass bytes to feedparser/extractor; preserve relative-URL/base-URL resolution and encoding, existing timeout/fallback behavior and explicit `allow_private_hosts` opt-in. Normalize DNS failures into typed/ValueError validation failures without leaking credentials. Use public fixture names/IPs and mocked transport/resolver; never probe real internal addresses.

Acceptance: allowed public chain succeeds; private/loopback/link-local/IPv6 and userinfo targets reject before transport; relative redirects resolve correctly; loops, missing Location, excess hops/bytes and timeouts fail boundedly; RSS XML MIME is accepted separately from HTML; extraction preserves article behavior; opt-in private-host behavior stays available. Clearly document remaining validation-versus-connect DNS gap unless transport pins the validated address while preserving Host/TLS validation and a controlled resolver-change test demonstrates it. Do not market redirect guards as complete SSRF prevention. If pinning requires a substantial transport redesign, return a bounded design follow-up rather than broadening this PR.

Verify: `python -m pytest -q tests/test_content_processor.py tests/test_reader_service.py tests/test_outbound_fetch.py tests/test_media_processor.py tests/test_podcast_api.py`. INPUT-01 can consume normalized DNS error type; independent sync owner must not also edit net.py. More targeted testing may select one-off API tests locally, with full file run at integration.

## INPUT-01

**P2: Invalid sync input is a client response, not 500 (ready; assign to sync owner)**

Own existing `ghostwriter/app/api/sync.py`, `ghostwriter/app/api/feeds.py`, `ghostwriter/tests/test_feeds.py`; new `ghostwriter/tests/test_sync_validation.py`. This is not a separate parallel owner if the cross-platform sync PR owns the same endpoints. Either include this small behavior in that PR or land it first.

Acceptance: malformed/mixed valid-invalid comma-separated digest UUIDs return 422 and do not partially process; whitespace/duplicates/empty string preserve valid behavior; no change to one-off digest privacy or response DTOs. Deterministic DNS failure during feed creation/update/sync returns an intentional non-500 validation response using FETCH-01's normalized error. Batch request validation failure must not partially write prior feeds. Subsequent retry with resolved DNS succeeds. Keep schema/dirty-write conflict semantics for the separate sync contract task.

Verify: `python -m pytest -q tests/test_sync_validation.py tests/test_feeds.py tests/test_podcast_api.py`. Depends on FETCH-01's error contract for DNS acceptance; UUID portion can land first. ENV-01 must release `test_feeds.py` ownership before this starts.

## RETENTION-01

**P2: Retention ownership and complete digest deletion (design/contract prerequisite; no destructive implementation yet)**

First deliver a short retention contract + regression fixtures PR, not a broad automatic cleanup. Proposed docs path `docs/decisions/digest-retention.md` (or orchestrator-approved equivalent); new `ghostwriter/tests/test_digest_retention.py` for current behavior/target fixtures. Do not add knowingly failing CI tests: capture historical reproduction in test-marked expected failures with precise reasons only if repo conventions allow, otherwise in a standalone fixture harness/design appendix. Future implementation owner reserves existing `ghostwriter/app/worker/cleanup.py`, `ghostwriter/app/api/digests.py`, `ghostwriter/tests/test_digest_download_formats.py`, and an explicit deletion service if needed.

Confirmed cleanup/manual deletion removes parent/EPUB without articles/PDF; podcast digest references and independent media/cover/debug artifacts make blanket cascades unsafe. Confirmed owner policy: preserve any episode-referenced source digest, block manual deletion and skip scheduled deletion until references are removed. Unknown historical orphans remain untouched. Remaining design work concerns ownership, persistence, concurrency and recovery details, not changing that policy. Recommended conservative scope is only artifacts unequivocally owned by the requested/deemed-expired digest, preserve independent/shared covers and episodes, and defer orphan backfill until reviewed. No blanket foreign-key enablement or new retention periods.

Design acceptance: ownership/dependency matrix for articles, EPUB, cached PDF, covers, episode source references/private one-off digest, media transcripts and debug files; preserve privacy of orphaned one-off sources; specify behavior on filesystem error, missing file, crash between DB/files and repeated retry. Include manual and scheduled deletion order and concurrency with download/generation. Once decisions are recorded, implement one deletion service for manual and scheduled paths and test rows/files/references, unrelated files, missing files, permission failure and idempotent retry. Any schema change requires orchestrator-allocated idempotent Alembic migration and fresh/previous-head upgrade tests.

Future verify: `python -m pytest -q tests/test_digest_retention.py tests/test_digest_download_formats.py tests/test_podcast_api.py` plus migration tests only if changed. This must be scheduled after any concurrent digest API/private-source changes.

## WALLABAG-01

**P2: Wallabag credential-aware token cache (ready, bounded hardening)**

Own existing `ghostwriter/app/services/wallabag_service.py`; new `ghostwriter/tests/test_wallabag_service.py`. Reserve narrowly `ghostwriter/app/api/config.py` only if explicit invalidation is chosen; no concurrent config owner. No bindery changes, so INGEST-01 can proceed if it only reads effective service settings.

Confirmed class-level token/expiry is shared across service instances and is not keyed to URL or credentials; from_db_or_settings bypasses constructor via __new__, so initialization changes must cover that path too. Scope cache to effective origin/account/client/credential generation (never expose secrets in logs/cache diagnostics) or simplify safe instance caching. Preserve effective DB/env fallback and expiry refresh. No new account management UI/schema.

Acceptance with mocked OAuth: same configuration reuses valid token; changed origin, username, password, client ID/secret never sends previous token to new configuration; expiry and failed refresh recover without poisoning other configurations; DB update service construction sees new credentials. Concurrent configurations remain isolated. Verify `python -m pytest -q tests/test_wallabag_service.py tests/test_newsletter_service.py` plus INGEST-01 tests after integration. Do not use real credentials or cross-origin token requests.

## RECOVERY-01

**P2: Digest failure/restart recovery contract (investigation prerequisite)**

Own new `ghostwriter/tests/test_bindery_recovery.py` + proposed `docs/decisions/digest-recovery.md` only; inspect `app/worker/bindery.py`, `app/main.py`, `app/services/podcast_service.py`, `app/worker/scheduler.py`. No mutable bindery overlap until INGEST-01 merged. Deliver controlled fault-injection evidence and one implementation-ready follow-up assignment, not queue-framework replacement.

Inject failure at artifact generation, article persistence, media consumed timestamp, remote processed marker, final completion, and process restart with synthetic content and mocked remotes. Correlate request/job rows/pipeline logs; report retry eligibility, duplicates/lost content, rows/files and current status. Recheck existing seen-article tests rather than redoing their proof. Confirm documented single-process/startup-fails-inflight behavior; do not add multiprocess support. Decide whether idempotency/recovery contract requires changing source acknowledgements or additional durable states before implementation. Any remote exactly-once guarantee must be qualified, not invented.

Verify new focused tests/harness against INGEST-01's accepted base, include cancellation/stale cutoff effects and deterministic retry. A docs/evidence PR is a complete bounded investigation deliverable; implementation PR is dependent on the accepted recovery contract.

## MEDIA-01

**P2: Media pipeline overlapping-run probe (investigation first, fix if bounded)**

Own existing `ghostwriter/app/worker/media_pipeline.py`, `ghostwriter/tests/test_media_retry.py`; new `ghostwriter/tests/test_media_pipeline_concurrency.py`. Read media API, scheduler and models; no model migration revision allocated yet. Independent of bindery source selection.

Confirmed guard only observes processing items before an awaited fetch, so two starts may both pass. Reproduce with deterministic asyncio barriers and mocked discovery/transcription; do not call Whisper/LLM. Include cancellation, transient fetch failure, retry and stale-item handling. If duplicate work is demonstrated, implement the smallest single-process exclusion/claim fix consistent with shipped one-process runtime, with unconditional release on success/failure/cancellation and accurate persisted run state. If persistent claim/schema or multiworker support is required, return design follow-up rather than claiming an in-memory lock solves distributed concurrency.

Acceptance: two simultaneous manual/scheduled calls cause at most one active processing/discovery owner and one paid-work mock call per eligible item; lock is released and later retry works after each failure/cancellation; existing single/bulk retry and counts remain correct. Verify `python -m pytest -q tests/test_media_pipeline_concurrency.py tests/test_media_retry.py tests/test_media_processor.py`. Migration changes, if proven necessary, require orchestrator handoff before editing models.

## Suggested launch waves

1. AUTH-01 + INGEST-01 + ENV-01 are independent implementation lanes (root integration/review uses remaining slot). ENV-01 uniquely owns conftest/dependency files.
2. FETCH-01 + WALLABAG-01 + MEDIA-01 after slot availability; INPUT-01 belongs to the coordinated sync lane and follows shared error/fixture contracts.
3. RETENTION-01 policy/evidence and RECOVERY-01 fault-injection can be research lanes while fixes run, but implementation waits for their specific contracts and overlapping owners. They are not permission to delete new classes of data or adopt a durable queue.

No package requires a new product audience decision to start its bounded scoped work. Retention deletion semantics and any changed retry/empty-edition public contract need an explicit recorded decision before destructive/contract-changing implementation.
