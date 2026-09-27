# Ghostwriter backend audit — 27 September 2026

Baseline: `cdb776d1d544bc6db0dd18a98cba1b9e86273f62`. Read-only audit of Python application, models, workers, migrations, tests, deployment entrypoint and container. No application source, task files, production data, `.env`, deployed service, provider account or production scheduler was changed. Parent agent is responsible for consolidation and product-wide conclusions.

## What is implemented

Ghostwriter is a substantial self-hosted content preparation and publishing server, not merely an RSS proxy. The product loop is: configure sources → periodically collect and clean new material → optionally summarize → package a reading digest → synchronize it to readers or download an EPUB/PDF → optionally turn selected digest material into a listenable podcast. A second podcast entry point accepts an ad hoc bundle of URLs or pasted text. It appears designed primarily as one trusted person's instance: first-admin registration closes after one account exists; feeds, normal digests, source integrations and instance configuration are shared. Some podcast data has explicit ownership and private one-off-source protections, but those do not make the whole product a multi-tenant service.

Implemented backend surfaces:

- RSS/Atom feed CRUD, bulk feed sync, changes since a timestamp, soft-deletion tombstones, raw/summarize mode, per-feed article limits, seen-history reset and feed-type checks (`app/api/feeds.py`).
- Manual and morning/noon/evening digest generation, durable status/progress rows, feed/article eligibility filtering, extraction, deduplication, summarization with raw fallback, ordered article records, cover generation/manual covers, EPUB output, on-demand cached PDF output, article HTML formatting, original-source reader extraction, downloads, deletion and combined mobile sync (`app/worker/bindery.py`, `app/api/digests.py`, `app/api/sync.py`).
- Wallabag saved-article ingestion with DB-editable credentials/mode, Gmail newsletters through OAuth with state/PKCE and label filtering. Gmail tokens are persisted under DATA_DIR with attempted 0600 permissions. Successful processing marks remote items as processed (`app/services/wallabag_service.py`, `newsletter_service.py`, `app/api/newsletters.py`). These external writes are part of the implemented normal digest workflow; none were exercised during this audit.
- Separate podcast/YouTube source subscriptions and a media queue. The media worker discovers entries, transcribes podcast audio / YouTube content using local whisper.cpp and/or OpenAI Whisper, summarizes when configured, retains completed transcripts, and allows retries. Completed transcripts are intended to be consumed by later digests (`app/worker/media_pipeline.py`, `app/api/media.py`, transcription/media/youtube services).
- Generated podcasts from one or multiple digests; independent podcast schedules; topic/source/keyword preferences; article feedback; weighted and balanced selection; one or two hosts; multi-stage LLM briefs/outlines/scripts; target length enforcement; OpenAI and ElevenLabs TTS; dialogue API fallback; chunk stitching and loudness processing through FFmpeg; episode numbering; MP3 ID3 chapters and Podcasting 2.0 chapter JSON; stream range requests; download; private RSS feed; feed artwork and configurable public base URL (`app/services/podcast_service.py`, `app/api/podcast.py`).
- Ad hoc podcasts from up to 20 URL/text sources, optional title/brief and per-episode generation overrides. URL ingestion uses a redirect-aware bounded HTML fetcher. Sources become a synthetic private digest. General digest listing/sync excludes these digests; access checks require episode ownership and fail closed for orphaned private digests. Existing tests cover these privacy boundaries (`one_off_podcast_service.py`, `test_podcast_api.py`).
- First-user setup/login, JWT web sessions, generated bcrypt-hashed API tokens for clients, revocation, legacy API_KEY compatibility, authenticated KOReader plugin generation, activity heartbeats, inactivity-based schedule disabling, log download and basic health/config endpoints.

## Architecture and state

FastAPI routers aggregate under `/api` in `app/api/router.py`; the same process serves a built Svelte SPA. `Settings` are cached environment settings and also read `.env` relative to the working directory. Runtime settings split between environment and SQLite models: `ClientConfig`, `WallabagConfig`, `ClientSettings`, reading `Schedule`, podcast preferences and podcast schedules. The split matters: changing one source does not necessarily change code that reads the other source.

SQLModel uses a synchronous SQLite engine (`app/core/database.py:26`) from async HTTP handlers and worker coroutines. Tables include feeds, digests/articles, seen articles, users/tokens, client configuration/activity, manual covers, media feeds/items/runs, podcast episodes/preferences/schedules/counters and article feedback. Content bodies and credentials are stored locally in DB/files; some response schemas mask secrets. They are not encrypted at rest by the application.

Digest and media workers are launched as in-process asyncio tasks; podcast tasks additionally retain references and support scheduling from the main event loop. APScheduler also runs inside the web process. Job rows persist state, but there is no external durable worker queue, lease owner protocol or resumable checkpoint execution. Startup converts in-progress digest and podcast rows to failed. This is coherent for a single-worker self-hosted installation with retry-on-failure expectations, and needs explicit constraints before changing deployment topology.

Docker runs a single uvicorn process after `alembic upgrade head` (`entrypoint.sh`). Fresh migration setup creates model tables and stamps the current head; unversioned historical databases are bootstrapped to revision 004 then repaired through the migration chain (`alembic/env.py:129`). Current head is 025. `init_db()` itself only creates missing tables: local `uvicorn` startup does not apply column migrations. A developer reusing an older database must run Alembic explicitly, even though the simple local dev-server command does not show that step.

The pipeline is highly concentrated: podcast service 4,909 lines, podcast API 1,564, bindery 1,408, podcast API tests 3,985. Existing abstractions and broad tests make incremental decomposition possible; these sizes are maintenance observations, not justification for a wholesale rewrite.

## Findings to prioritize

Priority labels are proposed restart priorities. Runtime-reproduced observations are distinguished from static evidence and deployment assumptions.

### P1 — Auth dependency leaves checked-out DB connections until garbage collection

Evidence: `app/core/security.py:75` obtains a session with `session = next(get_session())`. The generator's context manager is not retained for the request, and the reused session is never closed after subsequent queries. The proper `get_session` yield lifecycle exists at `app/core/database.py:46` and is already used via FastAPI dependency injection by other endpoints.

**Reproduced:** On an isolated DB, `engine.pool.checkedout()` was 0 before four unauthenticated setup-mode `verify_api_key` calls and 4 afterward with cyclic GC temporarily disabled. An explicit `gc.collect()` returned the count to 0. This proves resource release depends on GC. It does not establish a particular production outage threshold, but polling-heavy clients can exhaust or pressure the finite SQLAlchemy pool between collections. Fix with a yielded Session dependency or explicit scoped session and verify both success and exception paths.

### P1 — Configured authentication rate limiting is not connected to login/register

Evidence: `app/api/auth.py:138` login performs no rate-limit check; registration also does not. The only two calls to `check_auth_rate_limit(request)` occur at lines 347–348 after the unconditional return from `revoke_api_token`, and are unreachable. The limiter and default 10/min configuration exist in `app/core/rate_limit.py` and settings, creating a false impression that they protect authentication.

**Reproduced:** Twelve incorrect login attempts within one second returned twelve 401 responses, with no 429. No real account was involved. Wire checks into relevant public auth endpoints and add tests for thresholds and reset behavior. The current limiter is in-memory/per-process; document that if retaining the single-worker model.

### P1 — Digests cannot be built from media alone, or non-RSS integrations alone when no RSS feed is active

Evidence: `app/worker/bindery.py:206–212` returns immediately if the active RSS list is empty, before Wallabag/newsletter ingestion. Lines 415–421 return when RSS/Wallabag/newsletter lists contain no new articles, before completed media are loaded at lines 723–747.

**Reproduced:** An isolated completed podcast MediaItem was left unconsumed in two cases: no active RSS feeds, and one active RSS feed whose fetch was mocked to return zero articles. Both new digest rows were marked `completed` with zero articles, and neither EPUB existed. Thus the decoupled media pipeline can prepare usable content that never reaches a digest unless another source happens to provide a new item. Move the empty-content decision after all enabled sources have been considered; explicitly decide how zero-content jobs are represented.

### P2 — Digest deletion/retention leaves article bodies and generated PDFs behind

Evidence: `app/worker/cleanup.py:65–79` removes the EPUB and Digest row only. `app/api/digests.py:817–835` manual deletion has the same shape. DigestArticle defines a foreign key but no ORM relationship/cascade (`app/models/digest.py:142`); engine initialization does not enable SQLite foreign-key enforcement. PDFs are generated and cached separately by `app/api/digests.py:693–717`.

**Reproduced for scheduled retention:** Seeded one expired completed digest, one associated article, an EPUB and a PDF in temporary storage. Cleanup removed the digest/EPUB; one orphaned article remained and the PDF still existed. This violates a natural expectation of complete deletion/retention, grows stored content, and can leave podcast references dangling. Define lifecycle rules for digest articles, PDFs, covers/debug artifacts, episodes and media transcripts; implement explicit cleanup and migration/backfill if constraints change. Do not simply enable foreign keys without assessing existing orphans and delete ordering.

### P2 — UI-configured Wallabag summarize mode is ignored by the digest decision

Static evidence: `WallabagService.from_db_or_settings` correctly takes `db_config.mode` into its effective settings (`app/services/wallabag_service.py:59–72`). The worker instead checks the original environment-backed `self.settings.wallabag_mode` at `app/worker/bindery.py:616`. With default env mode `raw`, setting summarize in the DB/UI does not activate this stage; the inverse configuration can summarize when the UI says raw. Use one effective settings value. This was traced statically, not exercised against Wallabag.

### P2 — URL validation does not cover redirects in legacy content fetching

Static evidence: `app/services/content_processor.py:86–94` validates the initial URL then gives the URL to `feedparser.parse`; lines 252–257 do the same with `trafilatura.fetch_url`. The application does not revalidate each redirect target or pin the checked DNS result for those paths. Contrast with `reader_service.fetch_html_document`, which validates redirect targets and bounds content, and the media audio downloader's explicit redirect checks.

This is a concrete missing application guard, not a claimed successful SSRF exploit. The effective exploitability also depends on installed HTTP dependency behavior, DNS and deployment network access; no private-host request or hostile endpoint was used. Consolidate outbound URL handling or test these paths against a controlled redirect/DNS harness before exposing arbitrary source entry points to untrusted users. Private-host support is a deliberate opt-in needed by some self-hosted integrations and must retain a clear policy.

### P2 — Input/DNS failures in sync paths become 500s

**Reproduced:** `/api/sync?digest_ids=not-a-uuid` returns 500 because `UUID(id_str)` is constructed without input validation (`app/api/sync.py:155–158`). Validate the query as UUIDs and return a client error.

The full test suite additionally exposed `/api/feeds/sync` propagating `socket.gaierror` from URL validation (`app/api/feeds.py:160`, `app/core/net.py:25,72`) when DNS is unavailable. The initial failing test was environmental DNS resolution of example.com, not a failed feed business-rule assertion. A deterministic DNS-only mock made that same test pass. Convert DNS errors into an intentional validation/retry response and remove real DNS from unit tests.

### P2 — Packaging and verification setup drift

`requirements.txt` includes Alembic, bcrypt, python-jose, youtube-transcript-api and Mutagen, but `pyproject.toml` runtime dependencies omit those packages. Mutagen is imported unconditionally by podcast service and blocks the entire FastAPI test import if missing. Both the system interpreter and `ghostwriter/venv/bin/python` lacked it at audit start. Installing from declared project metadata alone cannot guarantee the runtime needed by the app. The documented requirements-based/container path is stronger, but multiple dependency manifests have drifted. Consolidate/derive dependency definitions and establish a reproducible tested environment.

Container builds additionally clone current whisper.cpp HEAD and install unpinned yt-dlp (`Dockerfile:51`, later runtime pip step), while most Python dependencies use broad ranges. This is a reproducibility risk rather than an observed production failure.

## Architecture limitations and follow-up investigations

- **Single-process assumption:** `app/main.py:118–149` fails all processing digests/podcasts on each startup and starts a scheduler. A second web worker can therefore fail jobs owned by the first; every process may schedule work. `generate_digest` checks and inserts a job without a DB-level exclusive lease (`bindery.py:1335–1393`). Keep/document one worker until explicit job ownership is designed. The shipped entrypoint presently uses one worker; no evidence of an actual multiworker deployment was inspected.
- **Media-run concurrency:** `media_pipeline.py:45` tests for an already-processing item, creates a run, then awaits fetch before claiming items. Concurrent manual/scheduled starts can both pass this check while no item is processing. Unique GUID/claim semantics and overlap should be tested. This was not reproduced as a production duplication event.
- **Restart behavior:** Failed jobs require retries; no resumable execution is implemented. Some durable articles/files and remote processed markers are committed before final digest completion, so fault injection around those boundaries would clarify retry semantics. A 30-minute digest stale-lock cutoff and 90-minute media cutoff are policy assumptions, not heartbeating leases.
- **Shared-instance versus ownership model:** first-admin setup, instance-global sources/settings/logs/normal digests, per-user tokens/preferences/feedback, and private one-off podcast sources coexist. This is not by itself a cross-tenant vulnerability because no general multi-user onboarding is provided. Preserve private-source checks and explicitly decide whether the target is personal self-hosting, a household, or hosted multi-user before adding users.
- **Retention scope:** completed media transcripts and media run histories have no obvious retention routine in the daily cleanup sequence; podcast debug prompts/audio artifacts and failed digest rows deserve a defined policy. This is a scope observation, not a claim that all storage has already grown uncontrollably.
- **Wallabag token cache:** class-level cached OAuth token is not keyed by instance/credentials and updating DB settings does not invalidate it (`wallabag_service.py:88–91`, `api/config.py:771–807`). A running server switched to another account/URL may temporarily reuse the old token. Review before expanding account management.
- **Event-loop work:** synchronous SQLite, EPUB generation and PDF rendering execute in async handlers/flows; some extraction work is correctly offloaded to a thread pool. Performance under simultaneous generation and polling needs measurement; no load benchmark was run.
- **Test gaps:** rich podcast/privacy/chapter and transformation regression coverage exists; missing runtime tests caught here include connection lifecycle, auth rate-limit wiring, zero-RSS/non-RSS-only source combinations, complete cleanup, and invalid sync identifiers. Provider synthesis quality, OAuth with a real account, whisper/FFmpeg system integration and deployed proxy configuration remain unverified.

## Verification performed

1. Read `AGENTS.md`, `tasks/lessons.md`, test conftest and pytest configuration before execution. The conftest already uses temp DATA_DIR/OUTPUT_DIR/LOGS_DIR, no legacy key, scheduler disabled, bcrypt rounds 4. That alone does not suppress `.env`, so the audit wrapper additionally changed cwd to a new temp directory and set `Settings.model_config['env_file'] = None` before app import. Provider/Wallabag/Gmail credentials and webhook config were blanked for the suite. Outbound INET socket connects were blocked. No real generation/provider requests were made.
2. Initial system-Python collection failed because Mutagen was missing. Repository venv also lacked Mutagen. After an ordinary sandbox network failure, an approved narrow escalation downloaded declared `mutagen==1.47.0` (194kB wheel) to `/tmp/epilogue-backend-audit-deps` only. No global/repo environment was modified.
3. `python3 /tmp/run_epilogue_backend_audit.py`: **243 passed, 1 failed, 858 warnings in 11.54s**. The failure was `test_feeds.py::test_sync_feeds` on external DNS resolution of example.com. This is the exact full-suite result; do not report an unqualified 244-pass run.
4. `AUDIT_MOCK_EXAMPLE_DNS=1 python3 /tmp/run_epilogue_backend_audit.py -k test_sync_feeds`: **1 passed, 243 deselected, 13 warnings in 0.16s**. The only added mock maps example.com to a public documentation fixture address; outbound network remains blocked. All 244 tests therefore passed across these two executions, with one requiring deterministic DNS injection.
5. Existing suite includes fresh/unversioned database bootstrap and podcast migration tests, EPUB/PDF generation/downloads, reader redirect protection, auth registration, media processing/retry, one-off privacy and podcast chapters. It does not prove every historical migration path nor successful end-to-end provider operation.
6. `python3 /tmp/epilogue_backend_probes.py` used a separate temp DB and files to reproduce connection retention, missing login rate limit, malformed sync ID, orphan article/PDF retention, and both media-only digest failures. Its only pipeline source call was mocked; Wallabag/Gmail configuration was mocked off. Probe output is exact below.

```text
POOL BEFORE 0
POOL AFTER 4 AUTH CHECKS 4
POOL AFTER GC 0
12 LOGIN STATUSES [401, 401, 401, 401, 401, 401, 401, 401, 401, 401, 401, 401]
INVALID SYNC UUID STATUS 500
ORPHAN ARTICLE COUNT 1
PDF LEFT AFTER RETENTION True
MEDIA-ONLY PROBE {'active_empty_rss': False, 'digest_status': 'completed', 'article_count': 0, 'media_consumed': False, 'epub_exists': False}
MEDIA-ONLY PROBE {'active_empty_rss': True, 'digest_status': 'completed', 'article_count': 0, 'media_consumed': False, 'epub_exists': False}
```

Temporary supporting artifacts: `/tmp/run_epilogue_backend_audit.py`, `/tmp/epilogue_backend_probes.py`, `/tmp/epilogue-backend-pytest.log`, `/tmp/epilogue-backend-pytest-dns.log`, `/tmp/epilogue-backend-probes.log`. These are audit scratch artifacts and are not durable project documentation unless copied during consolidation.

## Suggested restart order

First make dependency/bootstrap verification repeatable and repair the proven connection lifecycle, rate-limit wiring, source-combination and cleanup defects. Preserve existing behavior with focused regression tests. Then agree on trusted-instance scope, source/retention semantics and one-process job guarantees. Only after that prioritize product expansion and targeted decomposition of the podcast/bindery services. A new queue framework, multi-tenant rewrite or additional provider integration is not required to make the existing product materially more reliable.
