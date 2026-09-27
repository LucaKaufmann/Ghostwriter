# SYNC-EDITS-ANDROID: native feed sync v2

Base: accepted shared/server/identity commit `99fcda5`. Android owns the Room and UI adapter; shared v2 protocol and backend are unchanged. Room remains the sole feed/history database and moves from schema 8 to 9 without destructive fallback. Room 10 is reserved for delivery work.

## Behavior

- Every real Room 8 feed, including `locallyModified=false`, becomes a durable unresolved four-field proposal with null server version. Synthetic feeds, history, article relationships, EPUB paths, flags, and `lastFetched` survive migration. The frozen Room 8 fixture pins the deployed identity hash, tables, index, and foreign key independently of the production Room class.
- Local edit and delete allocate durable UUID operations in the same Room transaction as the feed update. Deletes hide the feed immediately while retaining an outbox row. A process-local sync gate binds each run to destination and binding generation. Sent operations replay identical payloads after restart until their exact receipt; later edits wait behind the head.
- First binding reconciles a complete server snapshot. Exact legacy matches adopt; mismatch, absence, and tombstone remain explicit decisions. Changed destination or server identity keeps the old binding suspended and its outbox visible until the user initiates review. Review creates a fresh scope and full reconciliation; cached feeds absent from the new destination are hidden pending explicit resolution. Credentials-only changes retain the binding.
- Pull applies feed changes and cursor in one Room transaction. Conflicts, validation rejections, and uncertain delivery retain proposals. Resolution actions create fresh operations with stable queue position before successors. Older conflict receipts cannot roll back a newer snapshot.
- Feed worker, settings sync, feed view model, and local repository writes use the shared v2 use case/native store. Legacy Android feed write entry points are disabled. A 404/405 v2 response retains pending edits and shows upgrade-required; older-server feed preview uses a read-only legacy GET and does not enter v2 state.
- Feed Manager shows both server values and local proposal values, including title, mode, enabled state, and cap, with explicit conflict, absence, delete, and rejection actions. E-ink pagination remains available when no attention cards are present.

## Verification

`Room8UpgradeProbeTest` opens an actual on-disk Room 8 database, migrates it with production `Migration(8,9)`, validates the generated Room 9 schema and rows after reopening, and verifies an injected migration failure rolls back cleanly to Room 8. `AndroidFeedV2StoreTest` exercises restart/replay, cursor rollback, delete and re-add ordering, binding changes and stale run tokens, conflict resolution with successors, and rejected correction/discard. `AndroidFeedV2UseCaseTest` drives the actual shared use case through the real Room store and deterministic fake remote for acknowledgement, conflict retention, partial failed push, and upgrade-required behavior. `Room9UiFixtureTest` creates a synthetic production-schema database for rendered emulator inspection; its export path defaults to the system temporary directory and can be overridden with `epilogue.uiFixtureOutput`.

Run with JDK 17 and Android SDK platform 35/build-tools 34:

```text
./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest :app:assembleDebug --offline --no-daemon --quiet
```

The actual debug APK was installed on an isolated emulator with a synthetic Room 9 fixture. Conflict/rejection/absence/hidden-delete cards and actions rendered. The root UI check selected **Keep server** and verified the proposal disappeared while the server title remained after force-stop/reopen. It selected **Delete anyway** on a hidden-delete conflict and verified a fresh queued delete UUID with base version 7 and hidden feed state after force-stop/reopen. No network/server outcome is implied by those UI checks. The fixture marks ambiguous absence and delete rows hidden, matching production reconciliation.

Final offline gate: **122 Android tests and 46 shared tests passed** with zero failures,
errors, or skips; `:app:assembleDebug` passed. Log:
`/private/tmp/epilogue-backlog-20260927/sync-android-final-gate.log`. The refreshed
synthetic Room 9 UI fixture is
`/private/tmp/epilogue-backlog-20260927/sync-android-ui-fixture.db`; the debug APK is
`app/build/outputs/apk/debug/app-debug.apk`.

The A-to-B destination test covers an empty B snapshot: the old cached feed is hidden
until explicit review, old-scope operations remain stored, and **Add to server** creates
a new complete four-field payload with no base version. A separate A-to-B test shows
old-scope legacy proposals cannot suppress generation from a reconciled B feed.

## Boundaries

The test fixture uses only `.invalid` synthetic URLs and no app/user data. No backend, shared, iOS, Gradle, lockfile, generated file, or delivery-ledger changes are included. Emulator inspection is synthetic, not a live server compatibility check. The later combined native/server test should verify real credentials, network failure handling, and UI actions end to end.
