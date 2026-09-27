# Native/shared autonomous PR work packages

Prepared 2026-09-27 from audit baseline `cdb776d`, with targeted current-source validation. No builds, tests, product source edits, PRs or implementation workers launched. Findings remain source-confirmed, not newly runtime-reproduced. Root AGENTS.md and tasks/lessons.md read. This is preparation for launch, not permission to change product semantics silently.

All packages inherit the [master backlog](backlog.md) and [worker launch prompt](worker-prompt.md).

## Shared launch rules

- Each package gets an isolated worktree/branch and sole owner. Only the orchestrator edits shared planning documents, allocates migration revisions, and integrates outputs locally; remote merges require separate authority. New native tests live with their owning package; test target/project manifest changes belong to native-toolchain owner until integrated.
- Common return: behavior/diff summary; exact branch/worktree/commit and PR URL; executed commands and actual results; baseline failures versus regressions; fixture limitations and unverified items; remaining risks and next action. Use Conventional Commit PR title, link evidence, attach created PR. No merge/deploy/provider calls. A required-check blocker means draft/unverified PR, never “done.”
- Native verification dependency `BUILD-NATIVE`: audit Android/shared tests stopped before execution because AGP 8.2.2 was missing offline; iOS compile used a stale generated project missing URL+Validation.swift, so a fresh KMP/Tuist setup is required before claiming source failure or success. No tests ran in either native baseline. No automatic dependency or Swift language upgrades to solve these blockers.
- Preserve Android’s hidden new-install Ghostwriter entry point and recovery controls for already-enabled configurations. Do not silently flip feature flags or disable existing integration. Preserve raw/summarize mapping and unlimited-article representation pending explicit contract decision.
- The short prefixes below denote exact existing paths: `A=app/src/main/java/com/example/epilogue`, `AT=app/src/test/java/com/example/epilogue`, `S=shared/src/commonMain/kotlin/com/example/epilogue/shared`, `ST=shared/src/commonTest/kotlin/com/example/epilogue/shared`, `I=EpilogueIOS`.

## CONTRACT-01

**Settle feed sync and local delivery contracts (orchestrator, prerequisite)**

**Priority:** P1 enabler; cannot send unrestricted parallel agents into sync/persistence.

**Outcome:** A separate contract PR with a compact approved contract, plus concrete schema/interface amendment before launching affected implementation packages. Own one new tracked contract document; do not edit product code in this step.

**Must settle:** (1) concurrent web/device edits: baseline version, dirty fields, conflict policy and what old clients may write; (2) durable delete versus edit/re-add ordering, idempotency, server identity and URL identity; (3) per-article identity, normal-run dedup, explicit regenerate behavior, limit overflow, failed/filter-rejected inputs, and retention of delivery identities after history cleanup; (4) what counts as partial versus failed generation and sync. Do not equate publication timestamp to an article delivery ledger.

**Confirmed owner invariants:** newer server feed state wins concurrent conflicts while the local proposal remains available for explicit resolution; normal local editions deliver once across history deletion, with explicit regeneration. Compatibility and persistence are now specified in the [accepted contract](../contracts/feed-sync-and-local-delivery.md); this section retains the original launch scope. **Implementation direction:** unchanged clients never write; pending edits are acknowledged individually against their sent version; deletion intent survives offline/restart and is not cleared by pull; normal local editions deliver an item once with explicit regeneration separated; failed/capped items remain eligible. Preserve partial usable results while exposing failures, rather than turning all ingestion errors into empty success. The contract was frozen before dependent implementation; current results are indexed in [project state](../project-state.md).

**Evidence:** shared FeedSyncUseCase pushes all feeds, then clears all dirty flags after a successful push; iOS native path separately repeats both behaviors. Android normal insert/update do not call WithSync variants. Android publication cursor moves before generation; iOS selection uses prefix(maxArticles) with no seen-item query. Server sync overwrites differences and intentionally preserves omitted feeds.

**Done:** example tables cover two devices+web, edits during in-flight push, delete offline/reconnect, delete versus re-add, repeated local generation, failures, same-date/no-date items, capped overflow, history retention, and client downgrade/older server compatibility. Exact fields/migrations/owner approved; no generic “dirty flag fix” assignment.

## BUILD-NATIVE

**Reproducible native/shared build and test baseline**

**Priority:** P1 verification enabler; safe to launch now, independently of backend fixes.

**Outcome:** Document and automate actual clean native setup, then establish Android/KMP tests and regenerated iOS simulator build/tests.

**Own:** `README.md` native setup paragraphs only; `I/README.md`; `I/Makefile`; `.github/workflows/native-checks.yml` (new); `I/Tuist/Package.swift`, `I/Workspace.swift`, `I/Tuist/ProjectDescriptionHelpers/Project+Templates.swift`, `I/App/Project.swift`, `I/Modules/{Domain,Data,ContentProcessing,AIServices,EPUBGeneration,GhostwriterClient}/Project.swift` only for reproducible build/test wiring. Root/shared/app Gradle files and lockfiles require coordinated scope extension after evidence of a real prerequisite defect; don't upgrade dependencies speculatively.

**Forbidden:** feature changes, feature-flag changes, editing generated `.xcodeproj`/workspace files as source, mass Swift concurrency cleanup, release signing, distribution, credentials committed in CI.

**Deps:** none for exploration; PRs requiring iOS test-target changes serialize behind this owner. Load using-tuist-generated-projects and xcodebuildmcp-cli skills before building; inspect installed tools.

**Acceptance/checks:** clean isolated checkout resolves declared versions; build shared XCFramework before Tuist generation (Makefile currently has this path while README shortcuts omit it); fresh generated project includes URL+Validation.swift; run `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon`; build release EpilogueShared XCFramework and freshly generated iOS simulator target with signing disabled; discover and run actual relevant test schemes. Document JDK/SDK/Tuist/Xcode versions, cache/network needs, exact commands, baseline defects. CI should reflect actual available runners and skip neither silently nor by reporting green dummy jobs. No real services required.

## ANDROID-FILES

**Android unique digest artifacts and safe legacy file ownership**

**Priority:** P1, ready now; independent of CONTRACT-01.

**Outcome:** Each new generated digest receives its own immutable output path; removing one history entry cannot remove another live entry's file, including pre-existing duplicate-path rows.

**Own:** `A/service/EpubGenerator.kt`; `A/data/repository/DigestRepository.kt`; `A/data/local/DigestDao.kt` if a live-reference query is required; `AT/service/EpubGeneratorTest.kt`; new `AT/data/repository/DigestRepositoryTest.kt`.

**Forbidden:** feed/delivery schema changes, content selection changes, automatic rewriting/deleting of existing books, retention policy changes.

**Deps:** BUILD-NATIVE for final verification; serialize ANDROID-DELIVERY after ANDROID-FILES because both touch DigestRepository/DigestDao. No product decision required.

**Acceptance:** two manual runs same day and repeated same-period runs produce distinct readable files; older digest content unchanged; deleting/retaining one does not remove the other's file; legacy rows sharing a path retain file until final reference is removed; failed writes don't replace valid artifacts. Test temp files and repositories without real feeds/AI. Existing source writes date+period with truncating FileOutputStream and cleanup deletes paths without reference protection.

**Checks:** focused generator/repository suite, Android unit suite; prove output bytes/ZIP entries, not just different filename strings. Include legacy duplicate path case and failed file creation.

## ANDROID-DELIVERY

**Android durable article delivery progress**

**Priority:** P1; blocked on CONTRACT-01, SYNC-DELETE and ANDROID-FILES integration, not safe as a one-line cursor move.

**Outcome:** EPUB/history failure, partial article extraction failure, or a per-feed cap cannot permanently skip eligible articles. A completion commits only the delivery progress represented in a durable usable digest.

**Own:** `A/data/repository/ArticleRepository.kt`, `A/service/DailyDigestWorker.kt`, `A/data/repository/DigestRepository.kt`, `A/data/repository/FeedRepository.kt`, `A/data/local/{DigestDao,FeedDao,FeedEntity,EpilogueDatabase}.kt`, `A/di/DatabaseModule.kt`; exact new delivery-identity entity/DAO path must be allocated in CONTRACT-01 before worker launch; new `AT/data/repository/ArticleRepositoryTest.kt`, new `AT/service/DailyDigestWorkerTest.kt`, ANDROID-FILES's repository tests by sequential ownership. Read domain Feed and ProcessedArticle; extend owned files only after contract determines necessity.

**Forbidden:** backend/API sync protocol changes, changing optional custom-export failures from best-effort into mandatory digest failure without decision, feature flag behavior, broad Room refactor. No provider calls.

**Deps/serialization:** CONTRACT-01, SYNC-DELETE, ANDROID-FILES, BUILD-NATIVE; cannot overlap Android feed persistence changes in SYNC-EDITS/SYNC-DELETE. Orchestrator allocates Room schema version after inspecting integrated HEAD.

**Acceptance:** inject EPUB creation failure, DB finalize failure, cancellation/restart, one bad item among good items, maxArticles overflow, same-date/missing-date/late-arrival inputs; retry retains eligibility without repeating already-delivered articles according to CONTRACT-01; forced regeneration preserves its approved semantics. Crash point between artifact creation and DB commit cannot lose delivery. Existing-store migration retains history/settings if schema changes. Date-only cursor adjustment alone does not satisfy partial/capped cases.

**Checks:** fixture worker/repository integration, temporary Room migration/transaction tests if changed, Android suite. Add no test that simply asserts updateLastFetched happens later while skipping recovery behavior.

## SYNC-EDITS

**Feed synchronization concurrency safety across all execution paths**

**Priority:** P1; depends on CONTRACT-01 sync contract. Assign ONE coupled owner or orchestrator-sequenced contract/server/client PRs, never independent uncoordinated writers.

**Outcome:** stale unchanged clients cannot overwrite web/server edits; concurrent dirty edits are resolved according to approved version policy; edits made while a request is in flight remain pending until their own acknowledgement.

**Own affected seam:** `S/domain/CoreDomainModels.kt`, `S/ghostwriter/{CoreModels,GhostwriterApiClient,GhostwriterClientHandle}.kt`, `S/sync/{Ports,FeedSyncUseCase}.kt`; `A/sync/AndroidSyncAdapters.kt`, `A/data/remote/ghostwriter/{SharedGhostwriterAdapter,SyncModels}.kt`, `A/data/repository/{FeedRepository,GhostwriterRepository}.kt`, `A/data/local/{FeedDao,FeedEntity,EpilogueDatabase}.kt`, `A/domain/model/Feed.kt`, `A/di/DatabaseModule.kt`, `A/ui/feed/FeedViewModel.kt`; `I/App/Sources/Services/{FeedSyncService,SharedSyncUseCaseFactory}.swift`, `I/App/Sources/Views/FeedListView.swift`, `I/Modules/Data/Sources/Data/Repositories/FeedRepository.swift`, `I/Modules/Domain/Sources/Domain/{Models/Feed,Protocols/FeedRepositoryProtocol}.swift`, `I/Modules/GhostwriterClient/Sources/GhostwriterClient/{GhostwriterClient.swift,Models/FeedModels.swift,Models/SyncModels.swift}` (the shared sync bridge is in SharedSyncUseCaseFactory.swift, already owned above); `ghostwriter/app/api/feeds.py`, `ghostwriter/app/models/feed.py` and the feed-tombstone cleanup function in `ghostwriter/app/worker/cleanup.py` if CONTRACT-01 requires API/version support. The server stage receives that cleanup handoff after RETENTION-02 finishes; it must retain v2 tombstones. Exact Alembic and SwiftData migration files allocated centrally before implementation.

**Required PR split:** This is a coordination epic, never a single unrestricted cross-platform worker. After CONTRACT-01, root dispatches SYNC-EDITS-SERVER (backend models/endpoints and migration), then SYNC-EDITS-KMP (shared models/ports/client/use case and common tests), then SYNC-EDITS-ANDROID and SYNC-EDITS-IOS in parallel on the frozen contract, followed by a fixture integration check. Server changes must remain backward compatible until clients migrate. Each stage gets an exact subset of the ownership list and a separate PR; no worker owns all files at once. The first Android/iOS edit stages own the complete edit/delete outbox schema in Room9/SwiftDataV2; later deletion stages verify remaining behavior without adding fields to shipped migrations. Native versioning/serialization targets must be fixed in CONTRACT-01 before launch.

**Tests:** `ST/sync/FeedSyncUseCaseTest.kt`, `ST/ghostwriter/CoreModelsSerializationTest.kt`, `ghostwriter/tests/test_feeds.py`, `AT/data/remote/ghostwriter/SharedGhostwriterAdapterTest.kt`, `AT/data/repository/GhostwriterRepositoryTest.kt`, `I/Modules/Data/Tests/DataTests/FeedRepositoryTests.swift`, `I/Modules/GhostwriterClient/Tests/GhostwriterClientTests/GhostwriterClientTests.swift`; new integration fixture tests for two clients+web.

**Forbidden:** tenancy/isolation redesign, destructive conflict resolution guessed by implementer, dropping old client support without decision, treating missing list entries as delete, synthetic integration feeds pushed as normal feeds, simultaneous SYNC-DELETE/ANDROID-DELIVERY ownership.

**Acceptance:** web edit+stale unchanged Android and iOS preserve web value; offline dirty edit round-trips; two-device concurrent edit follows policy; push failure preserves mutation despite successful pull; an edit during successful push is not globally cleared; legacy fallback and native combined path obey same semantics; synthetic feeds stay excluded; upgrade/old-client compatibility explicitly tested.

**Checks:** shared contract tests, backend API fixture tests, both adapters and native repositories, applicable migration tests, combined two-client fixture integration. BUILD-NATIVE required to call native result verified. Backend schema changes follow Alembic fresh+previous revision rules.

## SYNC-DELETE

**Durable offline feed deletions**

**Priority:** P2 data integrity; after SYNC-EDITS. Same owner recommended because it mutates feed persistence and sync ordering.

**Outcome:** deleted feeds stay deleted locally through offline/restart and eventually delete remotely; pending deletion is acknowledged only when server application is confirmed.

**Own:** SYNC-EDITS's feed models/store ports/repositories/adapters/native feed service and mutation UI paths; `A/service/FeedSyncWorker.kt` only if retry scheduling changes; `I/Modules/Data/Sources/Data/Persistence/PersistenceController.swift` if migration needs it. The complete outbox schema is allocated in CONTRACT-01 and implemented by the first native SYNC-EDITS stages; this follow-on does not add fields to a shipped migration. Backend delete endpoint changes only if contract tests prove required. Extend the same feed sync/repository tests plus durable restart tests.

**Required PR split:** Also a coordination epic. CONTRACT-01 first defines the durable intent DTO/port and replay/acknowledgement policy. Root dispatches SYNC-DELETE-CORE for shared/backend contract changes (only if needed), then SYNC-DELETE-ANDROID and SYNC-DELETE-IOS for platform persistence and adapters with one owner per platform, each in a separate PR, then verifies combined replay/restart behavior. Root supplies precise new schema paths/revisions before dispatch. No worker guesses fields while another edits adapters.

**Forbidden:** deleting feeds merely absent from a push, clearing outbox on generic sync success, inferring delete/re-add precedence ad hoc, changing global ownership to per-user tenancy.

**Acceptance:** delete offline, terminate/restart, reconnect, remote timeout, duplicate replay, already-deleted remote response, full pull before acknowledgement, and delete-versus-edit/re-add all follow CONTRACT-01; a pull does not resurrect pending local deletion; retry bounded; failure retains intent. Local-only mode and switching/reconfiguring server destination must not send old deletion intents to the wrong server.

**Checks:** persistence restart/migration tests, shared/native/legacy parity tests, backend fixture DELETE idempotency if touched, combined sync integration after SYNC-EDITS. BUILD-NATIVE required.

## IOS-SYNC-STATUS

**Truthful iOS sync results and preserved pending writes**

**Priority:** P2; can design immediately, implement after SYNC-DELETE because dirty acknowledgement and FeedSyncService overlap.

**Outcome:** applying a received payload unsuccessfully is visible as partial/failure; no successful sync timestamp or mutation acknowledgement conceals failed required work; retry/fallback does not duplicate successfully applied work.

**Own:** `I/App/Sources/Services/GhostwriterSyncCoordinator.swift`, `I/App/Sources/Services/FeedSyncService.swift`, `I/App/Sources/Services/{ConfigSyncManager,DigestSyncService}.swift` only for structured ingestion results/cursor acknowledgement; `I/App/Sources/Views/SyncStatusBanner.swift` only if truthful status cannot use existing error surface; new `I/App/Tests/GhostwriterSyncCoordinatorTests.swift` and `I/App/Tests/FeedSyncServiceTests.swift`.

**Forbidden:** redefining feed conflicts or broad client/network rewrite, making heartbeat availability block all local reading, silently consuming cancellation, Swift 6 language migration.

**Acceptance:** injected config/feed/digest/schedule apply failures each preserve last confirmed success and failed component progress, produce visible failure/partial result, and remain retryable; failed push + successful pull retains dirty writes; cancellation stops; unsupported combined endpoint still uses working fallback; an application failure is not misclassified as endpoint absence; retry does not create duplicate digests. Exercise normal and forced full-sync entry points.

**Checks:** fixture component tests and temporary SwiftData ingestion integration, native simulator tests, UI evidence if status rendering changes. Existing source catches every apply error, logs it, returns true and updates lastSyncTime; applyFeedChanges also clears flags unconditionally.

## IOS-DELIVERY

**iOS local article identity, deduplication and explicit ingestion failure outcomes**

**Priority:** P1/P2 behavior decision; depends on CONTRACT-01 delivery contract. Do not assign “add lastFetched filter” autonomously.

**Outcome:** repeat normal editions do not repeat delivered items/provider work, while failed/limited items remain eligible; ingestion errors cannot masquerade as an empty feed.

**Own:** `I/Modules/Data/Sources/Data/Repositories/{ArticleRepository,DigestRepository,FeedRepository}.swift`, `I/Modules/Data/Sources/Data/Services/DigestGenerator.swift`, `I/Modules/Domain/Sources/Domain/Protocols/{ArticleRepositoryProtocol,DigestRepositoryProtocol,FeedRepositoryProtocol}.swift`, relevant existing `I/Modules/Domain/Sources/Domain/Models/{Feed,Digest,DigestArticle,ProcessedArticle}.swift`, `I/Modules/Data/Sources/Data/Persistence/PersistenceController.swift`, `I/App/Sources/Services/LocalDigestService.swift`; new delivery-state schema paths allocated after CONTRACT-01. Tests: `I/Modules/Data/Tests/DataTests/{ArticleRepositoryTests,DigestGeneratorTests,DigestRepositoryTests,FeedRepositoryTests}.swift`.

**Forbidden:** assuming all thrown errors mean intentionally filtered articles; silent AI-to-full-article behavior changes; dedup based solely on title/date; content identity shared with backend without explicit mapping; paying for summarization in tests.

**Acceptance:** run same feed twice; one new item; duplicate links; missing dates; cap overflow; extraction and AI failures; mixed success; all failures; intentional short-content filtering; cancellation; EPUB/persistence failure/restart; completed-history removal does not accidentally reset dedup if CONTRACT-01 promises persistent delivery identity. Partial success semantics and explicit regenerate exactly follow CONTRACT-01. No provider invocation for already-delivered items. Error surfaces distinguish empty sources from failed ingestion.

**Checks:** repository/generator fixture tests plus old-store upgrade tests for SwiftData changes; fresh simulator build/tests under BUILD-NATIVE. Current code hides per-item errors with try? and then hides whole-feed errors with try? in DigestGenerator; both layers need examination.

**Serialization:** after SYNC-DELETE on shared Feed/SwiftData files; IOS-RECOVERY follows IOS-DELIVERY on DigestGenerator/models. This is a cohesive owner across selection and commit, not a parser-only fix.

## IOS-RECOVERY

**Recover interrupted iOS local generation**

**Priority:** P2, scoped recovery; serialize after IOS-DELIVERY (or before with explicit handoff).

**Outcome:** an abandoned pending digest does not suppress later catch-up, while an actually active local generation still prevents duplicate work.

**Own:** `I/App/Sources/Services/LocalDigestScheduler.swift`, `I/App/Sources/Services/LocalDigestService.swift`, `I/Modules/Data/Sources/Data/Services/DigestGenerator.swift`, `I/Modules/Data/Sources/Data/Repositories/DigestRepository.swift`, `I/Modules/Domain/Sources/Domain/Models/Digest.swift` only if a durable generation state is needed; launch wiring in `I/App/Sources/EpilogueApp.swift`; `I/App/Tests/LocalDigestSchedulerTests.swift`, `I/Modules/Data/Tests/DataTests/DigestGeneratorTests.swift`. Schema paths only with central allocation.

**Forbidden:** claiming reliable timer-based iOS background execution, unlimited retries, merely ignoring every pending record and allowing duplicate active jobs, treating remote server jobs as abandoned local jobs.

**Acceptance:** cold restart with pending local record retries/resolves correctly; active foreground/background run is not duplicated; completed and intentionally failed/empty outcomes follow CONTRACT-01; cancellation and a second restart remain safe; stale legacy record without added fields handled. Audit source counts incomplete rows without errors as period coverage.

**Checks:** scheduler/generator fixture tests with persisted state across process/session simulation, native simulator launch/catch-up evidence where feasible; no real network or system scheduling guarantee claimed.

## ANDROID-OBSERVE

**Lifecycle-bound Android generation observation**

**Priority:** P2; ready now and can run in parallel with ANDROID-FILES.

**Outcome:** repeated generation and disposed SettingsViewModels do not retain forever observers or display completion from obsolete work.

**Own:** `A/ui/settings/SettingsViewModel.kt`, `A/service/DigestScheduler.kt` only if stable request-ID/Flow API required; new `AT/ui/settings/SettingsViewModelTest.kt`, relevant `AT/service/DigestSchedulerTest.kt`.

**Forbidden:** scheduling policy changes, changed feature flags, global worker cancellation on screen close, source selection changes.

**Acceptance:** repeated click/run cycles retain one relevant subscription; old WorkInfo terminal states cannot complete the current run; ViewModel disposal detaches observation but does not cancel intended durable worker; success/failure/cancel clears progress appropriately; enabled persisted Ghostwriter still routes to existing backend path.

**Checks:** coroutine/lifecycle/WorkManager fixture tests, Android unit suite; BUILD-NATIVE required to claim execution. Current source calls observeForever on each local run and never removes it.

## ANDROID-FILTER

**Distinguish promotional exclusion from AI failure**

**Priority:** P3, after ANDROID-DELIVERY because ArticleRepository overlaps.

**Outcome:** model-declared promotional content stays excluded; transient AI errors preserve current full-article fallback.

**Own:** `A/service/OpenAIService.kt`, `A/data/repository/ArticleRepository.kt`, `AT/service/OpenAIServiceTest.kt`, ANDROID-DELIVERY's `AT/data/repository/ArticleRepositoryTest.kt`; typed result model path allocated within service/domain only if needed.

**Forbidden:** changes to prompt tone/length/model/provider, abandoning full-content fallback, real AI calls, treating cancelled calls as fallback content.

**Acceptance:** sentinel is filtered; network/provider error falls back; valid summary retained; fidelity path unchanged; rejected/failed eligibility follows CONTRACT-01/ANDROID-DELIVERY rather than accidentally counting as delivery. Source presently returns null for both sentinel and errors, then caller includes original article.

**Checks:** fixtures for sentinel/error/valid/cancellation plus repository behavioral tests.

## Suggested native launch graph

Immediately launchable once requested: BUILD-NATIVE, ANDROID-FILES, ANDROID-OBSERVE (independent owners). Orchestrator resolves CONTRACT-01 in parallel. Then ANDROID-FILES + SYNC-DELETE → ANDROID-DELIVERY → ANDROID-FILTER; CONTRACT-01 → SYNC-EDITS → SYNC-DELETE → IOS-DELIVERY → IOS-RECOVERY; SYNC-DELETE → IOS-SYNC-STATUS, but IOS-SYNC-STATUS's FeedSyncService ownership must wait until SYNC-DELETE's handoff or be folded into the SYNC-EDITS owner. ANDROID-DELIVERY cannot overlap SYNC-EDITS/SYNC-DELETE Android feed persistence changes; choose one lane order and pin prerequisite commits. BUILD-NATIVE precedes acceptance/ready-for-review status of every native implementation, although code work may begin independently. Do not turn this graph into one agent per finding running all at once.

Confirmed product choices: normal local editions deliver once with explicit regeneration; concurrent edits preserve the newer server version and retain the local proposal for explicit resolution. These choices are settled; backend feature-flag launch/platform priority can remain unchanged for reliability PRs. Native podcast parity, UI redesign, broad concurrency migration, and SaaS isolation are separate product milestones, not audit-remediation assignments.
