# SYNC-EDITS-IOS result

Branch: `codex/sync-edits-ios`, based on `99fcda5d554e313fa7b4faf713d50731c55fe98e`. This package activates the shared feed v2 use case on iOS with SwiftData V1→V2 migration, durable mutation queue and binding, explicit conflict and previous-server resolution, and a v2-only active feed sync path. The combined v1 sync response no longer applies feed rows. Old-server feeds are available through a read-only preview.

## Verification

- Captured independent unversioned V1 SwiftData store migrates through the production plan, retains three feeds, a digest and article, creates two full-field legacy proposals regardless of the old dirty flag, and reopens twice: `DataTests/SwiftDataMigrationProbeTests`, simulator pass (`/private/tmp/feed-v2-migration.xcresult`).
- App unit suite includes real exported KMP `FeedSyncV2UseCase` → SwiftData store apply/conflict runs, rollback, cursor failure, durable delete visibility, immutable replay and successor, destination replacement, synthetic-feed isolation, cancellation, server-wins conflict, newer pull, and legacy A→B prebinding safety. Corrective disk-store regressions cover prebinding deletion visibility; rejected create, edit, and delete discard; a successor after Keep server; corrected rejected edit base version; stale and cross-scope resolution; and invalid input rollback. Rejected-delete cases verify reopen, a newer pulled server snapshot, and a successor after an acknowledged edit. `xcodebuild test -workspace Epilogue.xcworkspace -scheme Epilogue -destination 'platform=iOS Simulator,id=3B168BD4-853C-4709-B0BB-DA65DA0B534F' -only-testing:EpilogueTests CODE_SIGNING_ALLOWED=NO` passed **33/33** (`/private/tmp/feed-v2-delete-correction-app.xcresult`); focused store tests passed **24/24** (`/private/tmp/feed-v2-delete-correction-focused.xcresult`).
- Simulator UI fixture navigates and renders conflict, rejection, absent-server, and delete resolution states: `EpilogueUITests/EpilogueScreenshotTests/testFeedResolutionFixture`, pass after fixture isolation (`/private/tmp/feed-v2-ui-correction.xcresult`). It verifies visible actions and navigation; it does not select an action or prove its persistence. Native store tests cover persistence behavior.
- `git diff --check` passes. No generated project or lockfile is included.

## UI evidence

- [Feed list with attention rows](assets/SYNC-EDITS-IOS/attention.png)
- [Conflict resolution](assets/SYNC-EDITS-IOS/conflict.png)
- [Rejected proposal](assets/SYNC-EDITS-IOS/rejected.png)
- [Absent server row](assets/SYNC-EDITS-IOS/absent.png)
- [Pending delete conflict](assets/SYNC-EDITS-IOS/delete.png)

Independent Sol review found reconciliation/resolution defects; corrective commits `574375c` and `ef2145f` address them. The final narrow review returned no actionable findings (`/private/tmp/epilogue-backlog-20260927/ios-delete-correction-review.log`).

## Integration notes

- The app test harness and UI fixture are compiled only in DEBUG. The UI fixture requires `-ui-testing`, `-feed-v2-ui-fixture`, and screenshot mode, and seeds the same in-memory container injected into repositories and SwiftUI. A fixture launch cannot clear the disk-backed app store.
- `DigestSyncService` and `ConfigSyncManager` remain owned by their separate packages. Integrate their truthful outcome changes with the coordinator before claiming combined sync status complete.
- No live Ghostwriter server was used in these native tests. The shared KMP/server live contract fixture is tracked separately.
