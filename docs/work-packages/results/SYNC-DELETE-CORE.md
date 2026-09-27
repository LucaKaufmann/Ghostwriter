# SYNC-DELETE-CORE live contract gate

Base: `e4daa4a2404682cd12384fc8b1e379bb1657884c`, branch `codex/sync-live-contract`, worktree `/private/tmp/epilogue-backlog-20260927/sync-live`.

Added one opt-in Android JVM test using the production `GhostwriterClientHandle` (Ktor OkHttp) against the existing disposable FastAPI journey fixture and its SQLite database. The test exercises the real `/api/feeds/changes-v2` and `/api/feeds/mutations-v2` routes: first full binding, zero-cap creation, uppercase frozen op ID with lowercase receipt and idempotent replay, two-client stale CAS conflict, delete/tombstone incremental pull, ordered re-add with stable feed UUID, and wrong-instance 409 with no write. A small semantic in-memory store proves the shared use case can acknowledge the original uppercase op ID and release its run gate; it is not evidence of native persistence.

`scripts/verify-feed-sync-contract.py` accepts only a supplied Python executable, chooses a free `127.0.0.1` port, starts the existing network-guarded journey fixture, waits at most 30 seconds for health, and starts the dedicated Gradle test with a 12-minute deadline. It terminates and reaps process groups on timeout/interruption and shuts down the fixture in `finally`. The test independently rejects any non-loopback fixture URL. The runner deletes stale XML, forces the test task to execute, then requires exactly one result with zero skips/failures/errors. The dedicated CI workflow installs JDK 17, Android SDK 35/build tools 34, Python 3.12, declared backend dependencies, and the native PDF/audio packages used by the existing fixture.

Local verification on macOS:

- `JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home ANDROID_HOME=/private/tmp/epilogue-backlog-20260927/android-sdk ANDROID_SDK_ROOT=/private/tmp/epilogue-backlog-20260927/android-sdk python3 scripts/verify-feed-sync-contract.py --python /private/tmp/epilogue-runtime-312/bin/python`: passed; dedicated XML reports 1 test, 0 skipped, 0 failures, 0 errors. The runner exited after reaping the disposable fixture process and deleting its temporary runner directory.
- `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon` without a live fixture: passed; Android 96/96, shared 47 total with the opt-in live test explicitly skipped and no failures.
- `git diff --check`: passed. The workflow has not run on GitHub yet.

The fixture invokes no real provider or production content. This gate checks the server/KMP wire contract and shared orchestration; Room/SwiftData migration, durable outbox replay after process death, local delete UI, and platform bypass removal remain separate native acceptance work.
