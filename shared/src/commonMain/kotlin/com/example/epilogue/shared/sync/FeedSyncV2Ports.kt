package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.FeedMutationV2
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2

data class FeedV2Destination(val normalizedBaseUrl: String, val configurationId: String)
data class FeedV2Binding(
    val destination: FeedV2Destination,
    val serverInstanceId: String?,
    val cursorVersion: Long?,
    val firstReconciliationComplete: Boolean,
    val generation: Long,
    val suspended: Boolean = false
)
data class FeedV2RunToken(val value: String)
data class SentFeedMutationV2(
    val opId: String,
    val url: String,
    val sequence: Long,
    val sentRevision: Long,
    val payload: FeedMutationV2
)
data class FeedV2WorkSummary(
    val eligible: Int,
    val blockedConflicts: Int,
    val rejected: Int,
    val unsentSuccessors: Int,
    val needsResolution: Int
) {
    val pending: Int get() = eligible + blockedConflicts + rejected + unsentSuccessors + needsResolution
}

sealed class FeedV2RemoteResult<out T> {
    data class Success<T>(val value: T) : FeedV2RemoteResult<T>()
    data class HttpFailure(val status: Int, val code: String?) : FeedV2RemoteResult<Nothing>()
    data class TransportFailure(val message: String) : FeedV2RemoteResult<Nothing>()
}

sealed class FeedV2StoreResult<out T> {
    data class Success<T>(val value: T) : FeedV2StoreResult<T>()
    data object Busy : FeedV2StoreResult<Nothing>()
    data object StaleBinding : FeedV2StoreResult<Nothing>()
    data object StaleSentRevision : FeedV2StoreResult<Nothing>()
    data class Failure(val message: String) : FeedV2StoreResult<Nothing>()
}

interface FeedV2ConfigurationPort {
    suspend fun currentDestination(): FeedV2Destination?
}

interface FeedV2RemotePort {
    suspend fun getFeedChangesV2(
        destination: FeedV2Destination, sinceVersion: Long?, serverInstanceId: String?
    ): FeedV2RemoteResult<FeedChangesV2Response>
    suspend fun postFeedMutationsV2(
        destination: FeedV2Destination, batch: FeedMutationBatchV2
    ): FeedV2RemoteResult<FeedMutationBatchResultV2>
}

/**
 * Native implementations persist binding, proposals, immutable sent payloads, and server
 * snapshots together. Each semantic method is one transaction that checks the run token and
 * persisted destination generation. The process-local gate spans network I/O; it is released
 * on cancellation. All local edits/deletes and conflict resolution are native semantic
 * transactions too, never direct row edits. Legacy rows become proposals regardless of the
 * old dirty flag. Synthetic URLs are excluded from every operation.
 */
interface FeedV2StorePort {
    suspend fun beginSyncRun(destination: FeedV2Destination): FeedV2StoreResult<FeedV2RunToken>
    suspend fun endSyncRun(token: FeedV2RunToken)
    suspend fun getServerIdentity(token: FeedV2RunToken): FeedV2StoreResult<FeedV2Binding?>
    suspend fun suspendBinding(
        token: FeedV2RunToken, binding: FeedV2Binding, reason: String
    ): FeedV2StoreResult<Unit>
    /** Complete snapshot only. Legacy rows, even dirty=false, become retained proposals. */
    suspend fun reconcileAndBindFullSnapshot(
        token: FeedV2RunToken, destination: FeedV2Destination, snapshot: FeedChangesV2Response
    ): FeedV2StoreResult<FeedV2Binding>
    /**
     * Atomically mark first send and return immutable eligible URL heads, at most maxItems.
     * Replay returns the identical op ID, base, fields and sent revision after timeout.
     * One URL has one head; successors wait. Busy/stale/failure are typed, not an empty list.
     */
    suspend fun loadPendingMutations(
        token: FeedV2RunToken, binding: FeedV2Binding, maxItems: Int
    ): FeedV2StoreResult<List<SentFeedMutationV2>>
    suspend fun pendingSummary(
        token: FeedV2RunToken, binding: FeedV2Binding
    ): FeedV2StoreResult<FeedV2WorkSummary>
    /**
     * Remove only the matching op ID + sent revision. Apply current only if its version is
     * not older than the stored server snapshot. A newer observed snapshot blocks any
     * successor for explicit resolution; never silently rebase it over that snapshot.
     * A delete acknowledgement may rebase a waiting re-add on its tombstone version and
     * must preserve the server UUID.
     */
    suspend fun acknowledge(
        token: FeedV2RunToken, binding: FeedV2Binding, opId: String, sentRevision: Long,
        current: FeedSnapshotV2?
    ): FeedV2StoreResult<Unit>
    /** Retain both current server snapshot and the original proposal; block URL successors. */
    suspend fun recordConflict(
        token: FeedV2RunToken, binding: FeedV2Binding, opId: String, sentRevision: Long,
        current: FeedSnapshotV2
    ): FeedV2StoreResult<Unit>
    /** Retain proposal/code/message and block URL successors until correction or discard. */
    suspend fun recordRejection(
        token: FeedV2RunToken, binding: FeedV2Binding, opId: String, sentRevision: Long,
        code: String, message: String?
    ): FeedV2StoreResult<Unit>
    /** Apply ordered changes and cursor atomically; never overwrite pending local proposals. */
    suspend fun applyServerChangesAndCursor(
        token: FeedV2RunToken, binding: FeedV2Binding, changes: FeedChangesV2Response
    ): FeedV2StoreResult<Unit>
}
