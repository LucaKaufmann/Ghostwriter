# SYNC-EDITS-KMP implementation handoff

Prepared 2026-09-27 from the accepted [feed sync and local delivery contract](https://github.com/LucaKaufmann/Ghostwriter/blob/codex/contract-01-sync-delivery/docs/contracts/feed-sync-and-local-delivery.md), [scoped mobile dispatch notes](mobile.md#sync-edits), integration checkout, and the server worker's current v2 route/service shape. This is a read-only design handoff: no implementation, build, commit, or PR is claimed. Root must pin the exact verified server base after its pending review before dispatch.

## Existing seams and ownership

`shared/.../sync/FeedSyncUseCase.kt` calls v1 `syncFeeds` with **every** nonsynthetic feed, maps unlimited `maxArticles=0` to `10`, pulls timestamp changes, then calls `clearAllLocallyModified()`. Its `Success/Error/NotConfigured` subclasses are matched exhaustively by Android `FeedSyncWorker` and Swift `SharedFeedSyncUseCaseFactory`. `Ports.kt` has only full-list `FeedStorePort` operations. `GhostwriterApiClient.kt` exposes v1 `/feeds/sync`, `/feeds/changes`, and combined `/sync`; `bodyOrThrow()` reduces HTTP 409 to generic `Conflict`, losing the v2 `detail.code`. The server stage's new routes are `/api/feeds/changes-v2` and `/api/feeds/mutations-v2`; responses use `server_instance_id`, `server_version`, `changes`/`results`, and FastAPI errors use `detail.code` (not a top-level `code`).

Keep the old exported constructors, interfaces, DTOs, `FeedSyncOutcome` subclasses, and legacy tests source-compatible during the KMP-only stage. Add separate v2 models, transport port, store port, and `FeedSyncV2UseCase`; do not inject it into existing native callers yet. Keep old v1 methods available only for source/export compatibility in this shared PR. They are **not** an error or upgrade fallback for v2. The full server/KMP/native sequence is one unreleased integration; the KMP PR alone cannot claim native feed sync safety.

Platform ownership gaps to hand to later stages:

| Platform | Paths that must converge on durable v2 sync |
| --- | --- |
| Android | `FeedSyncWorker`/`AndroidSyncAdapters` use shared v1; `GhostwriterRepository.syncFeeds` can write through both `SharedGhostwriterAdapter` and legacy Retrofit; `SettingsViewModel.runDigestViaGhostwriter` around line 218 and `performInitialGhostwriterSync` around line 1562 call it directly. `FeedViewModel` uses plain insert/update/delete and direct `deleteFeedByUrl`, bypassing durable intents. Preserve simultaneous ANDROID-OBSERVE lifecycle changes when later editing SettingsViewModel. |
| iOS | `FeedSyncService.sync` uses the Swift shared bridge, while `pushLocalFeeds` independently calls native `GhostwriterClient.syncFeeds`, maps zero to ten, and `applyFeedChanges` overwrites/deletes rows and globally clears flags. `GhostwriterSyncCoordinator.performFullSync` runs that push alongside heartbeat, then applies v1 feed data from combined `/sync`; fallback calls `FeedSyncService.sync`. `SharedSyncUseCaseFactory` exports old bridge adapters. `FeedListView` directly saves/deletes SwiftData feeds and invokes sync/deletion. Digest/config/schedule portions of combined sync may remain, but its feed section must not update v2 state. |

## Proposed additive KMP surface

Place wire types in a narrowly named `ghostwriter/FeedSyncV2Models.kt`, transport methods in `GhostwriterApiClient.kt`, and v2 orchestration/ports in `sync/FeedSyncV2UseCase.kt` and `sync/FeedSyncV2Ports.kt`. These are proposed Kotlin signatures to implement and compile-check, not a request to change the accepted server JSON:

```kotlin
@Serializable data class FeedChangesV2Response(
    @SerialName("server_instance_id") val serverInstanceId: String,
    @SerialName("server_version") val serverVersion: Long,
    val changes: List<FeedSnapshotV2>
)
@Serializable data class FeedSnapshotV2(
    val kind: String, val id: String, val url: String, val version: Long,
    val title: String? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
    val mode: String? = null,
    @SerialName("max_articles") val maxArticles: Int? = null
)
@Serializable data class FeedDirtyFieldsV2(
    val title: String? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
    val mode: String? = null,
    @SerialName("max_articles") val maxArticles: Int? = null
)
@Serializable data class FeedMutationV2(
    @SerialName("op_id") val opId: String, val url: String, val kind: String,
    @SerialName("base_version") val baseVersion: Long?,
    val fields: FeedDirtyFieldsV2? = null
)
@Serializable data class FeedMutationBatchV2(
    @SerialName("server_instance_id") val serverInstanceId: String,
    val mutations: List<FeedMutationV2>
)
@Serializable data class FeedMutationResultV2(
    @SerialName("op_id") val opId: String, val status: String,
    val current: FeedSnapshotV2? = null,
    val code: String? = null, val message: String? = null
)
@Serializable data class FeedMutationBatchResultV2(
    @SerialName("server_instance_id") val serverInstanceId: String,
    val results: List<FeedMutationResultV2>
)
```

The v2 decoder must validate UUIDs, exact stored URL keys, `kind/status` values, complete four-field active snapshots, tombstones, nonnegative versions bounded by `2^53-1`, and `0` as valid `maxArticles`. The v2 writer must encode **only** dirty nonnull keys; test serialized JSON so default nullable properties never become explicit null keys. An upsert with null base needs all four fields; delete has no `fields`. Keep `Long` as the wire/version type; never convert to `Double`, timestamps, or `Int`. A missing/invalid required field is an invalid response, not an empty feed list. Avoid a broad change to the existing Ktor JSON client configuration; use focused DTO/serializer validation as needed.

```kotlin
interface FeedV2RemotePort {
    suspend fun getFeedChangesV2(
        sinceVersion: Long?, serverInstanceId: String?
    ): FeedV2RemoteResult<FeedChangesV2Response>
    suspend fun postFeedMutationsV2(
        batch: FeedMutationBatchV2
    ): FeedV2RemoteResult<FeedMutationBatchResultV2>
}

sealed class FeedV2RemoteResult<out T> {
    data class Success<T>(val value: T) : FeedV2RemoteResult<T>()
    data class HttpFailure(val status: Int, val code: String?) : FeedV2RemoteResult<Nothing>()
    data class TransportFailure(val message: String) : FeedV2RemoteResult<Nothing>()
}
```

Implement those methods with the real Ktor `HttpClient` and `@SerialName` DTOs. First/full pull omits both query parameters; bound incremental pull sends both. Mutation always sends observed instance ID. Parse bounded/safe FastAPI `detail.code` on non-2xx before generic `GhostwriterApiException` mapping: `409/server_changed` suspends binding, v2 `404/405` is `ServerUpgradeRequired` (native clients must provide a v1 **read-only preview** on explicit user request; the shared v2 use case returns the upgrade outcome without applying unversioned rows, and no v1 write or cursor/ack application is allowed), auth and 422 are failures. HTTP 200 is still untrusted until response instance and outcome identities are checked. Do not route these through `GhostwriterRepository.syncFeeds` or Swift `GhostwriterClient.syncFeeds`.

The native store port should expose semantic **atomic operations**, rather than a KMP callback pretending to be a Room/SwiftData transaction:

```kotlin
data class FeedV2Destination(val normalizedBaseUrl: String, val configurationId: String)
data class FeedV2Binding(
    val destination: FeedV2Destination, val serverInstanceId: String?,
    val cursorVersion: Long?, val firstReconciliationComplete: Boolean
)
data class SentFeedMutationV2(
    val opId: String, val url: String, val sequence: Long,
    val sentRevision: Long, val payload: FeedMutationV2
)

interface FeedV2ConfigurationPort {
    suspend fun currentDestination(): FeedV2Destination? // null means local-only
}
interface FeedV2StorePort {
    suspend fun getServerIdentity(): FeedV2Binding?
    suspend fun reconcileAndBindFullSnapshot(
        destination: FeedV2Destination, snapshot: FeedChangesV2Response
    ): FeedV2StoreResult
    suspend fun loadPendingMutations(
        binding: FeedV2Binding, maxItems: Int
    ): List<SentFeedMutationV2> // atomically freeze/mark first send
    suspend fun acknowledge(
        binding: FeedV2Binding, opId: String, sentRevision: Long,
        current: FeedSnapshotV2?
    ): FeedV2StoreResult
    suspend fun recordConflict(
        binding: FeedV2Binding, opId: String, sentRevision: Long,
        current: FeedSnapshotV2
    ): FeedV2StoreResult
    suspend fun recordRejection(
        binding: FeedV2Binding, opId: String, sentRevision: Long,
        code: String, message: String?
    ): FeedV2StoreResult
    suspend fun applyServerChangesAndCursor(
        binding: FeedV2Binding, changes: FeedChangesV2Response
    ): FeedV2StoreResult
}
```

`FeedV2StoreResult` should distinguish applied, stale binding, stale sent revision, and storage failure, with counts/cursor where useful. The native implementations own transaction boundaries and persisted server snapshot/proposal separation. `loadPendingMutations` is a transactional claim: mark first send before network I/O, return one eligible head per exact URL (up to 100 independent URLs), and replay the same stored `opId/baseVersion/fields/sentRevision` after timeout. A binding-scoped run gate or durable claim lease must keep manual/background sync from sending the same URL concurrently; a timed-out lease may resend only the immutable payload. A sent row is immutable. Every local edit must atomically update the local visible state, increment `mutationRevision` and persisted per-server/per-URL sequence, and append a new operation; a delete also hides the feed atomically. Native conflict correction/discard APIs must preserve the old proposal until the explicit choice and use a new op ID for correction. The shared fake store can enforce these semantics but cannot prove native durability or migration.

Expose a new outcome, leaving old `FeedSyncOutcome` untouched:

```kotlin
sealed class FeedSyncV2Outcome {
    data class Complete(val applied: Int, val pulled: Int) : FeedSyncV2Outcome()
    data class Partial(val applied: Int, val pulled: Int, val pending: Int,
                       val conflicts: Int, val rejected: Int, val phase: String?) : FeedSyncV2Outcome()
    data class Failed(val phase: String, val message: String) : FeedSyncV2Outcome()
    data object NotConfigured : FeedSyncV2Outcome()
    data object ServerUpgradeRequired : FeedSyncV2Outcome()
    data object ServerChanged : FeedSyncV2Outcome()
}
```

## Use-case order and compatibility gates

1. Read the configured destination and persisted binding. Local-only returns `NotConfigured` without touching outbox. A changed normalized URL/configuration UUID suspends old bound intents, even if credentials changed independently. Never treat an already completed binding as a new first setup.
2. For an unbound destination or pre-upgrade store, do a **complete full v2 pull first**, verify response instance, then atomically reconcile/bind server rows, tombstones, cursor, and local proposals. Pre-upgrade rows are proposals regardless of the old dirty flag: matching rows adopt version; differences, tombstones, or absent URLs remain explicit `needs_resolution`. An absent pre-upgrade row cannot be auto-uploaded. Genuinely post-upgrade unbound intents bind without losing their fields; never-seen upserts can use null base, while existing/tombstoned URLs conflict, and unbound deletes cannot delete an existing remote feed.
3. For an existing binding, reject a changed destination or instance **before** any response apply, including HTTP 200. Check the instance after every pull and mutation. A greater-than-server cursor or `409/server_changed` suspends old cursor/outbox pending explicit reconciliation; no automatic replay to a replacement server.
4. Freeze one head operation per URL from durable storage and POST at most 100 items. Validate the **entire** result envelope before local writes: same instance, exactly one recognized result for each sent op ID, no extras/duplicates, and sane row URL/version. Missing/duplicate/unknown results retain the original sent payload and IDs for replay. Accepted siblings may be acknowledged independently only after this validation.
5. `applied` removes only the matching `opId + sentRevision`, even if a newer local revision exists. Apply `current` only if its version is at least the stored server version; an older replay receipt still acknowledges its exact old proposal and schedules pull, never rolls visible state backward. Rebase an unsent successor only on the accepted tombstone/feed version if no newer server snapshot was already observed. A conflicting/rejected head retains its proposal and blocks successors of that URL. Rejection persists code/message and stops automatic retry; conflict persists both latest server snapshot and dirty proposed fields. A delete followed by re-add stays ordered until delete ack; conflict blocks re-add.
6. Pull v2 changes in ascending version order and apply rows plus cursor in native transactions. No cursor or last-success timestamp may advance past a failed local apply. Pull must not overwrite pending local fields or hidden delete intent. A successful pull after a push failure is still `Partial`; `Complete` requires no unresolved pending conflict/rejection and successful push/pull phases. No generic success on transport/auth/invalid-response failure.

The shared PR should not change `Feed`'s existing exported constructor or `FeedStorePort`/`GhostwriterSyncPort` requirements. A replacement of those interfaces would immediately break old Android implementations and generated Swift adapters. Additive v2 types permit Android compilation and XCFramework export while platform stages are pending, but **all** native feed sync/write entry points above must be cut over or disabled with a visible upgrade state before integration is accepted. There must be no hidden flag or catch block that falls back to v1 bulk write after v2 fails.

## Required tests and verification for the implementation worker

- **Wire/MockEngine:** exact GET query omission on first pull; bound parameters; POST envelope and field omission; zero cap; delete fields absent; UUID/Long maximum; 100-item cap; FastAPI `detail.code`; 404/405 upgrade state; 409 changed instance; malformed active/tombstone/result data rejected. Assert v1 `/feeds/sync` is never called by v2, including transport and upgrade failures.
- **Stateful transaction fake:** initial full reconciliation of matching/different/absent pre-upgrade rows (including `locallyModified=false`), complete-snapshot-only binding, synthetic exclusion, post-upgrade unbound creates/deletes, local-only/config switch, instance change on 200 and 409, and no writes/cursor movement on rejected binding.
- **Immutable queue:** one sent head per URL with independent URLs batched, timeout replay byte/semantic equality and same op ID, edit during flight preserving successor, delete then re-add order and stable server UUID, rejected correction/discard with fresh op ID and blocked successors, no global dirty clear.
- **Receipts/pull:** accepted older receipt with newer local server snapshot, missing/duplicate/unknown outcomes, stale sent revision, conservative conflict for unrelated dirty field, pull row failure with unchanged cursor, successful pull after failed push yielding partial, and complete only when no unresolved work remains.
- **Cross-client fixtures:** web edit at version 5 with unchanged native at 4; two devices editing at 4; fresh/replaced instance at same URL. Confirm no timestamp last-writer logic or 0→10 conversion.
- **Compatibility:** shared unit suite, Android compile/tests, exported XCFramework and affected Swift bridge compile through actual Tuist pipeline. If additive models alone break Swift export, ask root for the smallest bridge ownership handoff; do not edit native files under KMP ownership. Native Room/SwiftData restart, upgrade, transaction, UI-resolution, and bypass-path tests remain mandatory in their later stages. An in-memory KMP fake is not proof of those properties.

## Concrete risks for root integration

The server route code is present in the separate server worker checkout, not the integration checkout inspected here; freeze its verified SHA and response/error shapes before KMP implementation. The current Ktor exception abstraction discards `server_changed` detail. Existing iOS combined sync can overwrite a newly reconciled v2 feed **after** v2 succeeds; Android SettingsViewModel can invoke a v1 bulk push before a digest; both are blockers to calling the integrated client safe. Native migration must preserve pre-upgrade rows as proposals even if `locallyModified` is false, and native atomicity remains unproved until Room/SwiftData tests run. Any server-v1 read-only preview used for an upgrade notice must not feed the v2 cursor, binding, or outbox acknowledgement.

## Orchestrator-approved port refinements (2026-09-27)

Implement the native migration investigation's explicit `suspendBinding`, typed `pendingSummary` and typed load/claim results, plus `beginSyncRun`/`endSyncRun`. The gate token is process-local on the singleton store, spans network I/O, and must release on cancellation/failure. Durable binding generation and immutable sent payload remain in storage across process death. All state-changing methods validate token and binding generation. Busy, stale binding and storage failure must not masquerade as an empty outbox. Use bridge-friendly methods rather than a suspend transaction lambda.

Remote calls must target the exact destination snapshot associated with the run. Pass destination to the remote port (or enforce equivalent immutable scoped adapter identity); a dynamic native client must reject a changed configuration rather than send old intents to a newly configured URL. Recheck current destination at phase boundaries and suspend stale binding before returning changed state. Credentials-only rotation preserves logical configuration identity. A native settings switch must atomically suspend/invalidate the old binding generation before enabling a new destination.

Keep sync bounded: at most100 mutations per network batch, truthful pending counts for work not completed, no unbounded immediate retry loop. Validate every result before any acknowledgement, including valid kind/URL/version for that operation and, for `applied` results, `current:null` only for a never-seen delete. A terminal `rejected` result has `current:null` and a nonblank rejection code; a `conflict` result requires a valid matching current snapshot. Rethrow cancellation and release run gate. The caller is responsible for scheduling later pending work; don't falsely report Complete after one batch when more remain.

Native resolution entry points can remain native semantic APIs but their transactional invariants must be documented here and exercised in later native tests. This shared stage cannot claim native persistence or migration proof.
