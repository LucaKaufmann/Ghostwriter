# SYNC-EDITS-IOS result

Branch: `codex/sync-edits-ios`, based on `99fcda5d554e313fa7b4faf713d50731c55fe98e`. This package activates the shared feed v2 use case on iOS with SwiftData V1→V2 migration, durable mutation queue and binding, explicit conflict and previous-server resolution, and a v2-only active feed sync path. The combined v1 sync response no longer applies feed rows. Old-server feeds are available through a read-only preview.

## Verification

- Captured independent unversioned V1 SwiftData store migrates through the production plan, retains three feeds, a digest and article, creates two full-field legacy proposals regardless of the old dirty flag, and reopens twice: `DataTests/SwiftDataMigrationProbeTests`, simulator pass (`/private/tmp/feed-v2-migration.xcresult`).
- App unit suite includes real exported KMP `FeedSyncV2UseCase` → SwiftData store apply/conflict runs, rollback, cursor failure, durable delete visibility, immutable replay and successor, destination replacement, synthetic-feed isolation, cancellation, server-wins conflict, newer pull, and legacy A→B prebinding safety. `xcodebuild test -workspace Epilogue.xcworkspace -scheme Epilogue -destination 'platform=iOS Simulator,id=3B168BD4-853C-4709-B0BB-DA65DA0B534F' -only-testing:EpilogueTests CODE_SIGNING_ALLOWED=NO` passed **22/22** (`/private/tmp/feed-v2-app-freeze.xcresult`).
- Simulator UI fixture navigates and renders conflict, rejection, absent-server, and delete resolution states: `EpilogueUITests/EpilogueScreenshotTests/testFeedResolutionFixture`, pass (`/private/tmp/feed-v2-ui-final.xcresult`). It verifies visible actions and navigation; it does not select an action or prove its persistence. Native store tests cover persistence behavior.
- `git diff --check` passes. No generated project or lockfile is included.

## UI evidence

- [Feed list with attention rows](assets/SYNC-EDITS-IOS/attention.png)
- [Conflict resolution](assets/SYNC-EDITS-IOS/conflict.png)
- [Rejected proposal](assets/SYNC-EDITS-IOS/rejected.png)
- [Absent server row](assets/SYNC-EDITS-IOS/absent.png)
- [Pending delete conflict](assets/SYNC-EDITS-IOS/delete.png)

## Integration notes

- The app test harness and UI fixture are compiled only in DEBUG. The UI fixture is activated only by `-feed-v2-ui-fixture` and uses the existing screenshot mode to avoid background sync.
- `DigestSyncService` and `ConfigSyncManager` remain owned by their separate packages. Integrate their truthful outcome changes with the coordinator before claiming combined sync status complete.
- No live Ghostwriter server was used in these native tests. The shared KMP/server live contract fixture is tracked separately.
