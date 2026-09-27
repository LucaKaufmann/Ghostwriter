# IOS-SYNC-STATUS digest ingestion prerequisite

Base: `99fcda5d554e313fa7b4faf713d50731c55fe98e`
Branch: `codex/ios-digest-sync-outcomes`
Scope: digest service and focused App tests only; coordinator integration is separate.

`DigestSyncService.sync()` and `processDigestsFromSync(_:)` retain `async throws`. A batch now preserves successful sibling digests, throws `DigestSyncIngestionError` with processed count and failed remote IDs when any required digest fails, and advances `lastDigestSyncTime` only after a fully successful batch. An empty successful batch advances the timestamp. Cancellation is rethrown, stops scheduling more downloads, and does not advance the timestamp. Download concurrency remains capped at three. Legacy article fetch must succeed before a remote ID is saved; a nonzero declared article count must match the fetched or embedded articles. Known remote IDs are skipped on incoming-payload retry so a successful sibling is not duplicated. The configured indexing-only mode and optional custom export remain intact.

Verification on 2026-09-27:

- `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ANDROID_HOME=/private/tmp/epilogue-backlog-20260927/android-sdk ./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon` — passed, 15 tasks.
- Tuist 4.152.0 `tuist install` and `tuist generate --no-open` — passed with declared package versions from cache.
- `xcodebuildmcp simulator test` on iPhone 16 Pro Max iOS 18.6, scheme `Epilogue`, isolated DerivedData, `-only-testing:EpilogueTests/DigestSyncOutcomeTests` — 6 passed, 0 failed. Fixtures use a temporary in-memory SwiftData `DigestRepository`, a suite-specific settings store, and injected planner/download/article inputs; no server/provider calls.
- `git diff --check` — passed.

Remaining integration and limitations:

- The coordinator must surface `DigestSyncIngestionError` as partial or failure and preserve its own confirmed-success state; this branch does not edit coordinator or feed/config paths.
- Historically incomplete remote digest rows already in SwiftData are still advertised as known IDs by the shared planner. Repairing these records requires a separate repository/planner contract and migration decision; this service prevents new missing-article rows from being recorded.
- A known indexed-only row whose remote filename changes before a later EPUB download cannot have its stored path updated by the current repository API. A later repository change may be needed for that uncommon case.
- Existing Swift 5.9 concurrency warnings in Data repositories and CoreData persistent-history truncation warnings appeared during the simulator run. The focused tests completed successfully.
