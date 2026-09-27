# iOS sync status outcome

Base at implementation start: `f71ed63` (feed v2 plus held digest and config prerequisites). Branch: `codex/ios-sync-status`.

The coordinator now uses one run policy for normal and forced sync. It records typed component and phase issues in `lastSyncError`, keeps successful siblings, and advances `lastSyncTime` only when all required components complete. Feed v2 runs independently; the combined response's v1 feed section is ignored. Only a combined fetch failure enters individual fallback. A 404/405 is labeled unsupported; transient fetch failure can recover through config, schedules, and eligible digest fallback. Cancellation stops later work and clears `isSyncing`.

After combined config reconciliation succeeds, schedules are fetched again before saving times. If config is incomplete, only enabled states from the combined payload are applied, preserving pending local times. The iOS config manager reports a shared Boolean false as `ConfigSyncIncomplete`, not a fabricated HTTP 500. The existing feed upgrade preview and server-change action inspect the aggregate's underlying feed error.

Review correction: a completed zero-article digest has no server EPUB, so both combined and legacy ingestion save its remote identity without downloading one. A nonempty digest still requires its EPUB when downloads are enabled. Normal cadence skips an empty digest payload but always ingests nonempty `newDigests` already returned by combined sync; both explicit Settings “Sync Now” actions use forced sync. This refines the initial handoff cadence plan, which would have delayed a new digest returned immediately after a recent empty sync. The obsolete v1 feed cursor is no longer read for combined sync, and a known-digest-ID read failure is reported without blocking independent config and schedule work.

Verification on 2026-09-27:

- `:shared:assembleEpilogueSharedXCFramework` with JDK 17: passed (15 tasks; fresh debug and release frameworks from corrected config source).
- `tuist install` and `tuist generate --no-open` (Tuist 4.152.0): passed.
- `xcodebuildmcp simulator build` for `Epilogue` Debug with isolated derived data: passed.
- `xcodebuildmcp simulator test` focused on `GhostwriterSyncCoordinatorTests` on iPhone 16 Pro Max iOS 18.6: 15 passed, 0 failed. Covers both entry points, component failures, 404/405/503 fallback, digest cadence, cancellation, configuration reads, fresh schedules, feed outbox retention/actions, and real SwiftData partial digest retry without duplicate IDs.
- After the review corrections and accepted feed integration, focused coordinator + digest simulator tests passed 24/24 and the full App suite passed 59/59 on the same simulator. The focused run includes zero-article combined/legacy indexing, recently fetched nonempty digest ingestion, and independent work after known-ID read failure. The test runner emitted a CoreData editable-model checksum diagnostic but reported no test failures.
- `git diff --check`: passed.

Existing native manual setting edits do not have durable offline change tracking; this change reports incomplete sync and protects in-flight local values but does not introduce a settings outbox. Historical already-incomplete digest rows are not repaired by retrying the sync.
