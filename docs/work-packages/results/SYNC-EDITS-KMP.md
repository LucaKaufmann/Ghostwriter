# SYNC-EDITS-KMP result

Base: accepted server `ad7fd3e5b05b14c72c4f413e28343b71e1e1fa8d` on `codex/sync-edits-kmp` in `/private/tmp/epilogue-backlog-20260927/sync-kmp`. This is the additive shared stage; native feed callers are not yet cut over.

## Delivered

- Added v2 feed snapshot, mutation, and response DTOs with JSON names matching the accepted FastAPI routes. The writer uses the Kotlin serializer with an explicit null `base_version`, omits unset dirty fields and delete `fields`, keeps `max_articles=0`, and bounds versions at `2^53-1`.
- Added Ktor GET `/api/feeds/changes-v2` and POST `/api/feeds/mutations-v2` transport on `GhostwriterApiClient`, with destination identity, first-pull query omission, FastAPI `detail.code`, and distinct HTTP/transport results. There is no v1 write fallback in the v2 path.
- UUID identities compare canonically because FastAPI returns lowercase receipt IDs even for uppercase UUIDs supplied by native clients. Frozen mutation payloads retain their original spelling across retries; acknowledgements use the original stored op ID and sent revision. New native intents should store canonical lowercase UUIDs.
- Added typed configuration, remote, and native-store ports and `FeedSyncV2UseCase`. It takes a process-local run token, full-reconciles before first claim, sends one bounded batch of at most 100 URL heads, validates the entire response envelope before acknowledgements, applies results by exact op ID and sent revision, then incrementally pulls. It suspends a changed binding on instance/destination mismatch, releases the gate on cancellation, and reports remaining or failed work as partial/failure.
- Preserved v1 shared constructors/interfaces/outcomes for staged source and Swift bridge compatibility. Two pre-existing common-test byte conversions now use `encodeToByteArray()` so Kotlin/Native can compile the shared test suite.

## Verification

- `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon`: passed (96 Android, 40 shared tests; zero failures). After the UUID review correction, focused `:shared:testDebugUnitTest` passed 44 shared tests.
- `./gradlew :shared:iosSimulatorArm64Test --no-daemon`: passed 44 shared tests with the permanent common-test portability fix and UUID regressions.
- `./gradlew :shared:assembleEpilogueSharedXCFramework --no-daemon`: passed, debug and release frameworks exported.
- Fresh `tuist install` and `tuist generate --no-open` in `EpilogueIOS`: passed. `xcodebuildmcp simulator build --workspace-path .../Epilogue.xcworkspace --scheme Epilogue --simulator-id 3B168BD4-853C-4709-B0BB-DA65DA0B534F --extra-args CODE_SIGNING_ALLOWED=NO`: passed. Existing Swift 6 sendability/deprecation warnings remain. The final serializer/validation edits did not alter exported signatures after this bridge compile.
- `git diff --check`: passed.
- Independent Sol full review found the UUID receipt issue; the correction at `0d18fb4` passed a second Sol review with no actionable findings.

## Tests and remaining integration obligations

MockEngine tests assert exact route/query/body and FastAPI error parsing. Stateful common tests cover full-pull ordering and invalid snapshot refusal, legacy match/mismatch/tombstone/absence proposals including synthetic exclusion, local-only/config switch, HTTP200/409 changed instance, malformed batch with no acknowledgements, reordered results by op ID, rejected/conflicting heads, timeout replay, edit during flight, delete then re-add, older receipt with newer observed snapshot, failed local pull apply, failed push plus successful pull, cancellation gate release, typed claim error, and the 100-item batch boundary.

Independent review identified an uppercase UUID response mismatch: FastAPI canonicalizes result op IDs to lowercase while hashing the original item, so changing a frozen payload on retry would produce `op_id_reused`. The correction compares UUIDs canonically for duplicate detection, result lookup, and server-instance checks while preserving the exact stored mutation payload and passing the original op ID/revision to native acknowledgement. Tests cover an uppercase frozen request with lowercase receipt, byte-identical timeout replay, case-variant duplicate operations/results, and uppercase instance equivalence.

The in-memory store fake models the native transaction contract but does not prove Room or SwiftData persistence, migrations, process-restart replay, cross-context serialization, or UI conflict resolution. Android/iOS stages must implement the semantic transactions and generation checks, disable all legacy feed write/pull bypasses, and verify real on-disk upgrade/restart behavior before integrated native sync is safe. No server, native, schema, CI, lockfile, generated project, provider, production-content or deployment changes were made in this stage. This shared prerequisite is published separately from native activation.

## PR review follow-up (2026-09-27)

PR99 comments4115376564/4115376566: disabling integration during full pull, push or incremental pull now returns NotConfigured without suspending the existing binding or applying an in-flight response; enabling the same destination resumes the immutable outbox. A failed incremental pull returns Failed, including when no mutation is pending; failed push followed by successful pull retains the existing Partial(phase=push) contract.

`./gradlew :shared:testDebugUnitTest :shared:iosSimulatorArm64Test --offline --no-daemon` passed on JDK17/task Android SDK, 46 tests on each platform. New fixtures cover disable/resume across all remote phases and timeout/401/500 with and without pending edits. Providers are mocked.
