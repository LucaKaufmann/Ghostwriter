# SYNC-EDITS-KMP result

Base: accepted server `ad7fd3e5b05b14c72c4f413e28343b71e1e1fa8d` on `codex/sync-edits-kmp` in `/private/tmp/epilogue-backlog-20260927/sync-kmp`. This is the additive shared stage; native feed callers are not yet cut over.

## Delivered

- Added v2 feed snapshot, mutation, and response DTOs with JSON names matching the accepted FastAPI routes. The writer uses the Kotlin serializer with an explicit null `base_version`, omits unset dirty fields and delete `fields`, keeps `max_articles=0`, and bounds versions at `2^53-1`.
- Added Ktor GET `/api/feeds/changes-v2` and POST `/api/feeds/mutations-v2` transport on `GhostwriterApiClient`, with destination identity, first-pull query omission, FastAPI `detail.code`, and distinct HTTP/transport results. There is no v1 write fallback in the v2 path.
- Added typed configuration, remote, and native-store ports and `FeedSyncV2UseCase`. It takes a process-local run token, full-reconciles before first claim, sends one bounded batch of at most 100 URL heads, validates the entire response envelope before acknowledgements, applies results by exact op ID and sent revision, then incrementally pulls. It suspends a changed binding on instance/destination mismatch, releases the gate on cancellation, and reports remaining or failed work as partial/failure.
- Preserved v1 shared constructors/interfaces/outcomes for staged source and Swift bridge compatibility. Two pre-existing common-test byte conversions now use `encodeToByteArray()` so Kotlin/Native can compile the shared test suite.

## Verification

- `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon`: passed (96 Android, 40 shared tests; zero failures). Final shared fixture changes were rerun with `:shared:testDebugUnitTest` successfully.
- `./gradlew :shared:iosSimulatorArm64Test --no-daemon`: passed with the permanent common-test portability fix and final expanded v2 fixtures.
- `./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon`: passed, debug and release frameworks exported.
- Fresh `tuist install` and `tuist generate --no-open` in `EpilogueIOS`: passed. `xcodebuildmcp simulator build --workspace-path .../Epilogue.xcworkspace --scheme Epilogue --simulator-id 3B168BD4-853C-4709-B0BB-DA65DA0B534F --extra-args CODE_SIGNING_ALLOWED=NO`: passed. Existing Swift 6 sendability/deprecation warnings remain. The final serializer/validation edits did not alter exported signatures after this bridge compile.
- `git diff --check`: passed.

## Tests and remaining integration obligations

MockEngine tests assert exact route/query/body and FastAPI error parsing. Stateful common tests cover full-pull ordering and invalid snapshot refusal, legacy match/mismatch/tombstone/absence proposals including synthetic exclusion, local-only/config switch, HTTP200/409 changed instance, malformed batch with no acknowledgements, reordered results by op ID, rejected/conflicting heads, timeout replay, edit during flight, delete then re-add, older receipt with newer observed snapshot, failed local pull apply, failed push plus successful pull, cancellation gate release, typed claim error, and the 100-item batch boundary.

The in-memory store fake models the native transaction contract but does not prove Room or SwiftData persistence, migrations, process-restart replay, cross-context serialization, or UI conflict resolution. Android/iOS stages must implement the semantic transactions and generation checks, disable all legacy feed write/pull bypasses, and verify real on-disk upgrade/restart behavior before integrated native sync is safe. No server, native, schema, CI, lockfile, generated project, provider, production content, PR, or deployment changes were made in this stage.
