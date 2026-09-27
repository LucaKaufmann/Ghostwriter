# iOS sync status outcome

Base at implementation start: `f71ed63` (feed v2 plus held digest and config prerequisites). Branch: `codex/ios-sync-status`.

The coordinator now uses one run policy for normal and forced sync. It records typed component and phase issues in `lastSyncError`, keeps successful siblings, and advances `lastSyncTime` only when all required components complete. Feed v2 runs independently; the combined response's v1 feed section is ignored. Only a combined fetch failure enters individual fallback. A 404/405 is labeled unsupported; transient fetch failure can recover through config, schedules, and eligible digest fallback. Cancellation stops later work and clears `isSyncing`.

After combined config reconciliation succeeds, schedules are fetched again before saving times. If config is incomplete, only enabled states from the combined payload are applied, preserving pending local times. The iOS config manager reports a shared Boolean false as `ConfigSyncIncomplete`, not a fabricated HTTP 500. The existing feed upgrade preview and server-change action inspect the aggregate's underlying feed error.

Verification on 2026-09-27:

- `:shared:assembleEpilogueSharedXCFramework` with JDK 17: passed (15 tasks; fresh debug and release frameworks from corrected config source).
- `tuist install` and `tuist generate --no-open` (Tuist 4.152.0): passed.
- `xcodebuildmcp simulator build` for `Epilogue` Debug with isolated derived data: passed.
- `xcodebuildmcp simulator test` focused on `GhostwriterSyncCoordinatorTests` on iPhone 16 Pro Max iOS 18.6: 15 passed, 0 failed. Covers both entry points, component failures, 404/405/503 fallback, digest cadence, cancellation, configuration reads, fresh schedules, feed outbox retention/actions, and real SwiftData partial digest retry without duplicate IDs.
- `git diff --check`: passed.

Final acceptance is pending integration of the separately reviewed iOS feed correction and a rerun of affected simulator tests. Existing native manual setting edits do not have durable offline change tracking; this change reports incomplete sync and protects in-flight local values but does not introduce a settings outbox. Historical already-incomplete digest rows are not repaired by retrying the sync.
