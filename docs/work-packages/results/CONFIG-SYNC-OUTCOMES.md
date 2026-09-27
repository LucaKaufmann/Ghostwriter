# Config sync outcome prerequisite

Base: `99fcda5d554e313fa7b4faf713d50731c55fe98e`
Branch: `codex/config-sync-outcomes`
Scope: shared config use case, its fixture tests, and iOS config manager error propagation. Coordinator integration is separate.

The shared `ConfigSyncUseCase` retains its Boolean API. Normal and pre-fetched config sync now run the same timestamp reconciliation. A newer local config must be uploaded before returning true; transport or not-configured upload results return false while retaining the local values and timestamp. HTTP 409 still refetches and applies server config; the sync reports success only if that reconciliation succeeds. Equal pre-fetched timestamps continue to apply the server payload, while equal normal sync timestamps remain unchanged. Save errors and cancellation propagate. `ConfigSyncManager.pushMinWordCount` now throws when its shared push returns false, matching its existing throwing apply and sync paths.

Review correction: the backend checks `client_updated_at` against its own current timestamp (within one second). Local-newer uploads now use the fetched server timestamp as that compare-and-set guard and upload the captured local values. A changed server version still produces 409 and a refetch. Before an upload and after its response or conflict refetch, the use case checks the captured local timestamp, schedule, and minimum word count; an in-flight local edit keeps the result pending instead of letting the response overwrite it.

Verification on 2026-09-27:

- `./gradlew :shared:testDebugUnitTest :shared:iosSimulatorArm64Test --no-daemon` with JDK 17 and the isolated Android SDK: passed after the final cancellation guards (21 tasks; 9 config fixtures each on Android and iOS, zero failures).
- `./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon`: passed; fresh debug and release XCFrameworks assembled (15 tasks).
- `tuist generate --no-open` (Tuist 4.152.0): passed.
- `xcodebuildmcp simulator build` for `Epilogue` Debug on iOS 26.5, isolated derived data, against that release XCFramework: passed. Existing Swift concurrency warnings remain in Data repositories; no config-sync compile errors.
- `git diff --check`: passed.

Correction verification: `./gradlew :shared:testDebugUnitTest :shared:iosSimulatorArm64Test --no-daemon` passed with JDK 17 and the isolated Android SDK (21 tasks; 13 config fixtures each on Android and iOS, zero failures). The fake server enforces the backend's one-second timestamp guard and covers both entry points, real concurrent server changes, and in-flight local edits. The prior XCFramework/App compile predates this internal Kotlin correction; the final combined coordinator build will consume the changed framework.

Coordinator follow-up: after config reconciliation, refresh schedules before applying schedule times; a combined response can be stale after a local config upload. If config failed with pending local fields, do not overwrite those times with stale server values. Test both success and failure cases while independently reporting enabled-state apply failures. The coordinator must surface false or thrown config results without advancing overall last success. This branch does not change feed or digest behavior.

This branch is held for the combined coordinator change; the review's stale-schedule and overall-success findings are coordinator-owned. Native manual setting edits do not consistently advance the config timestamp or enter a durable outbox. The in-flight value checks above prevent immediate response overwrite, but they do not make all manual edits durable across later offline syncs; that broader tracking remains outside this prerequisite.
