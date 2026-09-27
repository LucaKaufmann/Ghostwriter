# ANDROID-FILES result

Branch `codex/android-files-unique-artifacts`, base BUILD-NATIVE `8c7c148ab5bc9d59f7305f7b64d0e235e9d60f6f`.

New generated EPUBs reserve unique date/period-prefixed paths, flush archive bytes, and remove only their own failed output. Date formatters are per generation. History deletion, automatic retention and remote cache eviction check other persisted references in a Room transaction. Deletion uses the current stored path, preserving legacy shared files until the last reference is removed. Failed unlink retains the row for retry. No database schema or feed/delivery selection change.

Verification: JDK17.0.17, task-local AndroidSDK35/build-tools34, Gradle8.5. `./gradlew :app:testDebugUnitTest :shared:testDebugUnitTest --no-daemon` passed:87 Android and19 shared tests. New tests exercise actual generated EPUB content/unchanged older bytes, creation and serialization failure, in-memory Room legacy shared references, stale UI paths, failed/missing-file deletion, retention and cache cleanup. Fixtures only, no real sources/providers. Initial regression run found epub4j closes its underlying stream before fsync; a non-closing wrapper now keeps the descriptor open through the durability flush, and the rerun passed.

Room serializes the reference check/unlink/row delete with database writers. Filesystem unlink and DB commit are not one atomic transaction: a later DB failure can leave the final unreferenced history row with an already-missing file; repeating deletion treats absence as success. No orphan sweep or claim of power-loss recovery is made. Device/hardware behavior is not validated by Robolectric. Existing article-count duplicate-save policy is untouched; durable delivery semantics are a later package.

Independent Sol review and publication pending root closeout. Native hosted iOS CI is independent and still pending; Android hosted baseline passed.
