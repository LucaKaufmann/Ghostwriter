# ANDROID-OBSERVE result

Branch `codex/android-observe-lifecycle`, base `faa3927` (includes BUILD-NATIVE and ANDROID-FILES).

An immediate digest enqueue now returns its WorkRequest UUID. SettingsViewModel observes WorkInfo for that exact request, replaces the observer on a new run, and detaches it on success, failure, cancellation, or ViewModel disposal. A stale or mismatched WorkInfo ID cannot complete the current run. Starting a run clears previous completion, failure, error, and progress state. A persisted enabled Ghostwriter configuration continues through the backend path. Unique-work REPLACE policy and worker durability are unchanged; closing the ViewModel does not cancel WorkManager work.

Verification used JDK 17.0.17, Android SDK 35 and Gradle 8.5. `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon` passed: 95 Android and 19 shared tests, zero failures. The final focused SettingsViewModel fixture rerun passed after adding a mismatched-ID assertion. Fixtures cover repeat/replacement, stale terminal WorkInfo, success/failure/cancel, observer disposal, and persisted Ghostwriter routing. No device run or real provider calls were made. First test compile exposed a fixture WorkInfo constructor argument-order mistake; first fixture run reused a terminal ID on its second cycle. Both fixture issues were corrected before the passing runs. Initial sandbox denial on the shared Gradle cache was resolved by approved escalation; it was not a test failure.

Review: diff and tests checked locally; independent Sol review requested from orchestrator. No schema, scheduling policy, delivery, or source-selection change. The current ViewModel does not reattach to a durable request after process recreation; this package addresses observation lifecycle while the ViewModel is alive.

Final review identified a nullable WorkInfo emission before asynchronous enqueue persists the request. Root changed the observer to accept and ignore null, with a regression for initial/repeated null followed by success. Full suite rerun passed96 Android/19shared tests; targeted correction Sol review returned no actionable findings.
