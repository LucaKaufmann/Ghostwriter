# Config sync outcome prerequisite

Base: `99fcda5d554e313fa7b4faf713d50731c55fe98e`
Branch: `codex/config-sync-outcomes`
Scope: shared config use case, its fixture tests, and iOS config manager error propagation. Coordinator integration is separate.

The shared `ConfigSyncUseCase` retains its Boolean API. Normal and pre-fetched config sync now run the same timestamp reconciliation. A newer local config must be uploaded before returning true; transport or not-configured upload results return false while retaining the local values and timestamp. HTTP 409 still refetches and applies server config; the sync reports success only if that reconciliation succeeds. Equal pre-fetched timestamps continue to apply the server payload, while equal normal sync timestamps remain unchanged. Save errors and cancellation propagate. `ConfigSyncManager.pushMinWordCount` now throws when its shared push returns false, matching its existing throwing apply and sync paths.

Verification on 2026-09-27:

- `./gradlew :shared:testDebugUnitTest :shared:iosSimulatorArm64Test --no-daemon` with JDK 17 and the isolated Android SDK: passed after the final cancellation guards (21 tasks; 9 config fixtures each on Android and iOS, zero failures).
- `./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon`: passed; fresh debug and release XCFrameworks assembled (15 tasks).
- `tuist generate --no-open` (Tuist 4.152.0): passed.
- `xcodebuildmcp simulator build` for `Epilogue` Debug on iOS 26.5, isolated derived data, against that release XCFramework: passed. Existing Swift concurrency warnings remain in Data repositories; no config-sync compile errors.
- `git diff --check`: passed.

Coordinator follow-up: after config reconciliation, refresh schedules before applying schedule times; a combined response can be stale after a local config upload. If config failed with pending local fields, do not overwrite those times with stale server values. Test both success and failure cases while independently reporting enabled-state apply failures. The coordinator must surface false or thrown config results without advancing overall last success. This branch does not change feed or digest behavior.
