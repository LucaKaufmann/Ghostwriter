# Mobile and shared-code audit — 2026-09-27

## Scope and confidence

Read-only source audit of Android (`app/`), Kotlin Multiplatform (`shared/`), and iOS (`EpilogueIOS/`), including UI entry points, repositories, generation, scheduling, sync, manifests and test suites. Root AGENTS.md and existing lessons were read. Tuist and XcodeBuildMCP skills guided verification. No application was launched, no provider request or deployment was performed, and no source was modified. Findings below distinguish source-proven behavior from execution results. This is not an exhaustive security review or a claim of release readiness.

## Product and implemented journeys

The mobile product is Epilogue, the reading companion and optional on-device generator for Ghostwriter. Its purpose is to turn chosen feeds into calm, finite reading sessions: EPUB digests grouped by feed, with full articles (Fidelity) or AI summaries (Briefing), then read/share/export them on a phone or e-ink reader. The backend product adds server-side schedules, synchronization, extra content sources and output formats.

Both apps implement:

- Feed creation, editing, enable/disable, deletion, processing mode and per-feed article limits.
- Feeds, History and Settings entry points; digest detail and paginated readers; EPUB sharing/export. Reader content comes from persisted digest articles rather than requiring a general-purpose EPUB renderer. Android supports volume-key page control and e-ink presentation; iOS uses CoreText pagination and can fetch original article content through Ghostwriter.
- Local RSS/Atom extraction, local OpenAI briefing, EPUB generation and a retained history. iOS additionally explicitly parses JSON Feed.
- Morning/noon/evening schedule selections, manual generation and launch-time catch-up.
- Optional Ghostwriter URL/API-token configuration, heartbeat/config/feed/digest sync, server generation trigger/status polling, EPUB download, conditional PDF download, remote integrations/media management, logging/token/config controls.
- Optional document-folder export (Android Storage Access Framework; iOS security-scoped bookmarks).

Important availability difference: Android's `FeatureFlags.ghostwriterSettingsEnabled` is **false** (`app/src/main/java/com/example/epilogue/config/FeatureFlags.kt:5`). The settings entry remains visible only for already-enabled persisted configurations (`ui/settings/SettingsScreen.kt:81`). New Android installs therefore cannot discover/configure the substantial backend feature set through the normal settings UI. iOS has `ghostwriterSettingsAvailable = true` (`EpilogueIOS/App/Sources/Views/SettingsView.swift:19`). This is an intentional release gate in code, not absent implementation, and should be an explicit product decision before more parity work.

The mobile code has podcast/YouTube *source management and summary inclusion* controls. Do not equate these with the backend's richer generated-podcast production experience; the primary mobile navigation remains feeds/digests/settings, without a dedicated generated-podcast player flow.

## Architecture and ownership

### Android

- Kotlin 1.9.22, AGP 8.2.2, min API 33/target 35; Compose, Hilt, ViewModels/StateFlow, Room and WorkManager (`build.gradle.kts`, `app/build.gradle.kts`).
- Three Room entities: Feed, Digest, DigestArticle. Database version 8 has explicit 1→8 migration chain in `di/DatabaseModule.kt`. Schema export is disabled (`data/local/EpilogueDatabase.kt:7`).
- Settings use SharedPreferences; API keys use EncryptedSharedPreferences (`data/repository/SettingsRepository.kt:73`).
- Local pipeline: `DailyDigestWorker` → `ArticleRepository` → RSS fetch/date filter → promotional filtering → RSS-content-aware extraction/readability → optional OpenAI summary → `EpubGenerator` → optional custom export → digest/article history finalization.
- `DigestScheduler` uses independent WorkManager jobs for periods, immediate generation, catch-up, 15-minute feed sync and 30-minute digest sync. Local worker refuses generation when Ghostwriter is configured (`DailyDigestWorker.kt:64`).
- `GhostwriterRepository` defaults to KMP-backed `SharedGhostwriterAdapter` but retains Retrofit fallback paths. This adds compatibility but duplicates a large API/model surface.

### iOS

- SwiftUI, SwiftData, Tuist modules: Domain, Data, ContentProcessing, AIServices, EPUBGeneration, GhostwriterClient, App. iOS 18 minimum; manifests set Swift 5.9 language mode.
- Domain is not pure business logic: Feed/Digest/DigestArticle are SwiftData reference models. Main-actor repositories return those model objects through async protocols. The compile emitted Swift 6 sendability/isolation warnings for these boundaries.
- Settings use UserDefaults and Keychain. SwiftData initializes a single current schema; initialization failure calls `fatalError` (`Modules/Data/Sources/Data/Persistence/PersistenceController.swift:65`). There is no explicit versioned schema/migration plan here; existing-store upgrade testing is therefore important, though no migration failure was reproduced.
- Local pipeline: `LocalDigestService` or `LocalDigestScheduler` constructs parser/extractor/OpenAI/EPUB dependencies and invokes `DigestGenerator`.
- Background strategy: opportunistic charging-required BGProcessing request two hours ahead of the next period, hourly BGAppRefresh feed fetch, launch/foreground catch-up, notification reminders. This is best-effort background execution plus catch-up, not a guaranteed timer. `LocalDigestScheduler.swift:118` and `:174` show this split.
- `GhostwriterSyncCoordinator` orchestrates native combined-sync fast paths; fallback uses KMP bridges. `GhostwriterClient` is an actor that defaults to the shared client and retains native URLSession fallback. The roughly 1,400-line client and roughly 800-line bridge are maintenance seams, not completed elimination of duplicate networking/models.

### Shared KMP

- Builds Android library and static `EpilogueShared` XCFramework for device arm64, simulator arm64 and x64 (`shared/build.gradle.kts`).
- Owns portable domain DTOs, serializable API models, Ktor client and feed/config/digest sync use cases behind settings/store/network ports.
- Does **not** own UI, platform persistence, local content extraction, EPUB generation or OS scheduling. Those behaviors remain separate and have diverged.
- iOS manifests require the locally generated release XCFramework (`EpilogueIOS/App/Project.swift:57`; `Modules/GhostwriterClient/Project.swift:7`). `EpilogueIOS/Makefile` knows how to build it. Root/iOS README setup omits this prerequisite and may fail on a clean clone.

## Prioritized findings

### M1 — High: stale mobile feed state overwrites server edits during sync

**Source-proven path, not reproduced against a server.** Shared `FeedSyncUseCase.sync()` pushes before pulling (`shared/.../sync/FeedSyncUseCase.kt:31`), and `pushLocalFeeds()` serializes **every** local feed (`:69–85`), ignoring `locallyModified` and `serverUpdatedAt`. iOS's native fast path repeats this (`App/Sources/Services/FeedSyncService.swift:74–95`). Backend `/feeds/sync` overwrites title/active/mode/max whenever the client differs (`ghostwriter/app/api/feeds.py:167–182`).

Example: web changes a feed from Briefing to Fidelity; an unchanged phone later syncs its old Briefing value before reading server changes, restoring Briefing on the server. This undermines multi-device/web ownership. Dirty flags exist but ordinary Android add/update calls do not use the `WithSync` repository methods (`ui/feed/FeedViewModel.kt:57,63`; `data/repository/FeedRepository.kt:93,101`). Remediation should define conflict ownership, durable mutations/version checks, and test two clients plus web edits; merely filtering dirty flags is insufficient without consistent mutation marking.

### M2 — High: Android advances ingestion cursor before durable digest completion

`ArticleRepository.fetchArticles()` updates `lastFetched` to current wall-clock time when any article succeeds (`app/.../data/repository/ArticleRepository.kt:114–116`). The worker only generates EPUB and finalizes history afterward (`service/DailyDigestWorker.kt:101–134`). On EPUB/storage/finalization failure, retry refetches using the already-advanced cursor. Articles from the failed digest—and individual failed articles in a partially successful feed—can be excluded permanently from subsequent normal runs. The per-feed limit also truncates candidates before the cursor advances (`ArticleRepository.kt:74–76`). Date-only cursors are not equivalent to per-article delivery state.

Commit ingestion progress only after durable success, or track individual article identities/status so failed or capped items remain eligible. Regression tests should inject output failure and partial extraction failure.

### M3 — High: Android EPUB filename collisions corrupt history-file ownership

`EpubGenerator.writeEpub()` uses only day plus optional period (`app/.../service/EpubGenerator.kt:345–354`). Two manual runs on the same day write the same file using truncating `FileOutputStream`; repeated same-period scheduled runs also collide. Separate history records then refer to the same path, so opening an old record's file returns newer content. Deleting or retaining out an old record deletes that shared file (`data/repository/DigestRepository.kt:245–250`). iOS already uses timestamp + UUID filenames (`Modules/Data/Sources/Data/Services/DigestGenerator.swift`, `generateFileName`). Give Android each generated digest a unique durable filename and verify deletion ownership.

### M4 — High/medium: iOS local generation has no incremental article deduplication

`ArticleRepository.fetchAndProcessArticles(from:)` parses the feed and takes its first `maxArticles` entries, without consulting lastFetched or seen article IDs (`EpilogueIOS/Modules/Data/Sources/Data/Repositories/ArticleRepository.swift:52–75`). The parser returns feed items without any time cutoff (`Modules/ContentProcessing/Sources/ContentProcessing/Services/FeedParser.swift:22–44`). A lastFetched model property/repository method exists but this generation flow does not use it. Every morning/noon/evening/manual run can repeat the same current feed articles and repeat paid summarization. This is source-confirmed divergence from Android's incremental behavior; impact severity depends on whether repeated full snapshots are intended.

### M5 — Medium: offline mobile deletion is not durably synchronized

Android deletes locally and logs a failed remote DELETE (`app/.../ui/feed/FeedViewModel.kt:67–85`); iOS deletes/saves locally then uses `try?` on remote deletion (`EpilogueIOS/App/Sources/Views/FeedListView.swift:75–85`). Neither inspected flow retains a local tombstone/outbox retry. Backend feed sync is additive and deliberately preserves absent feeds (`ghostwriter/app/api/feeds.py:198`). Therefore the server retains a failed deletion and can reintroduce it during a full pull or later update. Add durable delete intents and acknowledge them only after successful server application.

### M6 — Medium: iOS combined sync reports success despite application failures

`GhostwriterSyncCoordinator.tryCombinedSync()` catches config/feed/digest/schedule application failures individually, logs warnings, and returns true (`EpilogueIOS/App/Sources/Services/GhostwriterSyncCoordinator.swift:177–206`). `performFullSync` then updates success time (`:124`). The fallback is skipped even when local application failed. The fast feed path also clears dirty flags unconditionally (`FeedSyncService.swift:117`) although preceding push failure is swallowed (`GhostwriterSyncCoordinator.swift:147–154`). Users can see a successful sync while content/config remains stale, and pending state may be cleared. Return structured partial failures, preserve failed mutations, and surface a truthful sync result.

### M7 — Medium: Android local generation result observation accumulates forever

Each `runDigestLocally()` registers a new `observeForever` observer (`app/.../ui/settings/SettingsViewModel.kt:152–171`) and does not retain/remove it. Repeated runs and destroyed ViewModels can keep obsolete observers alive and update stale state. Use a lifecycle-owned Flow/observer and observe the relevant work request.

### M8 — Medium: known iOS in-progress records can suppress catch-up after interruption

`LocalDigestScheduler.hasDigestCoveringLatestPeriod` counts incomplete records with no error as covering the period (`EpilogueIOS/App/Sources/Services/LocalDigestScheduler.swift:485–491`). `DigestGenerator` persists such a record before any network work (`Modules/Data/Sources/Data/Services/DigestGenerator.swift:59–73`). A process kill after insertion leaves no error and no completion, yet catch-up considers that period covered for the day. No stale-pending recovery was found in the examined launch path. Add ownership/lease age or recovery of interrupted jobs and tests for cold restart with an abandoned pending record.

### M9 — Lower priority: promotional rejection becomes a full-article fallback

Android `OpenAIService.summarizeArticle` returns null for the explicit `PROMOTIONAL_CONTENT` sentinel (`app/.../service/OpenAIService.kt:148–151`), but `ArticleRepository` treats every null as a summarization error and includes the original full article (`data/repository/ArticleRepository.kt:101–105`). The early promotional filter will catch some items; this issue concerns only promotional content that reaches the model. Use a distinct filtered result versus transient summarization failure.

## Behavior/parity decisions to settle

| Concern | Android local | iOS local |
|---|---|---|
| New-install backend setup | Hidden by release flag | Exposed |
| Incremental selection | Publication-date cursor, with durability issues above | Reprocesses current feed items |
| Extraction | Prefer full RSS content, readability fallback, promo heuristics | Always retrieves article URL |
| AI unavailable/fails | Falls back to full article | Drops failed article via `try?`; all failures become no-articles result |
| Briefing prompt | Under 150 words, calm bedtime tone, 4,000-character input cap | Under 250 words, full extracted input |
| Parallelism | All feeds parallel; articles within feed serial | Feeds and their articles parallel, no inspected concurrency cap |
| Scheduling | WorkManager plus all missed-period catch-ups | Opportunistic charging BGProcessing plus latest-period catch-up |
| Filenames | Date + period, overwrite risk | Date/time + period + UUID |
| Secrets | EncryptedSharedPreferences | Keychain |

These differences mean “feature parity” needs a written behavioral contract, not only matching screens. The coherent product direction inferred from README is finite calm reading across devices, with Ghostwriter as optional server orchestration; whether local generation is a fully supported independent product or a simpler fallback is not settled by the code.

## Tests and executed verification

Existing inventory: 9 Android unit-test files, 7 shared common-test files, 13 iOS unit-test files plus one screenshot UI-test file. Tests cover parser/extractor/AI/EPUB, repositories, client serialization/endpoints and scheduling calculations. Shared feed sync has two tests: successful pull/tombstones and preserving flags on push failure; it does not exercise server-edit conflicts. No Android instrumented test source files were found in the reviewed tree. GitHub workflows found here cover Ghostwriter, not mobile builds/tests.

Executed:

1. `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --offline --no-daemon`.
   - First sandbox attempt failed to write Gradle wrapper cache lock.
   - With normal cache permissions, wrapper became available, then Gradle configuration failed because `com.android.application:8.2.2` was not cached/resolvable in offline mode.
   - **Zero unit tests ran. This is an environment/dependency availability blocker, not a test failure.** No dependency upgrade was attempted.
2. XcodeBuildMCP availability/help discovery succeeded. Simulator inventory initially hit sandbox service restrictions; normal permissions successfully listed available runtimes.
3. XcodeBuildMCP simulator **compile only**, scheme Epilogue, existing generated workspace, iOS 26.5 simulator destination, `/tmp/epilogue-mobile-audit-derived`, `CODE_SIGNING_ALLOWED=NO`, no automatic package resolution.
   - Build failed in `FeedParser.swift:23,49`: `URL` has no member `validHTTPURL`.
   - **This is attributable to the existing generated project being stale:** source `Modules/ContentProcessing/Sources/ContentProcessing/Extensions/URL+Validation.swift` contains the helper, but the checked local generated ContentProcessing pbxproj does not include it. Tuist manifest globs should pick it up on regeneration.
   - Also emitted numerous Swift 6 future-error warnings for non-Sendable SwiftData models crossing repository actor/protocol boundaries and UserDefaults in Sendable settings.
   - No app launched; no iOS tests ran. Workspace regeneration and a fresh KMP build were deliberately left unverified at parent request to finish the audit without more toolchain repair. Do not report this stale-workspace failure as proof the current source cannot compile after correct setup.

Neither platform has a green baseline established by this audit. Next verification should use a clean clone/isolated checkout, resolve pinned dependencies, build the shared XCFramework, regenerate Tuist, run targeted suites, and perform fixture-only UI flows. Real background scheduling, e-ink device behavior, Keychain entitlements, release signing and cross-device synchronization need separate validation.

## Suggested restart slices

1. Establish reproducible mobile build/test baseline (including KMP prerequisite and CI), and decide the Android backend gate.
2. Fix data ownership before new features: feed-sync conflict semantics/outbox deletes; cursor durability and unique Android files; iOS pending-job recovery/deduplication.
3. Write a local/server/parity contract for selection, retries, empty digests, limits, retention, partial failures and what “sync succeeded” means.
4. Reduce duplicate network/DTO paths incrementally only after their fallback/version-support requirements are known; avoid a broad rewrite.
5. Bring iOS actor boundaries into an explicit safe model before switching Swift language modes; use immutable snapshots across worker boundaries instead of assuming persisted reference models are sendable.
