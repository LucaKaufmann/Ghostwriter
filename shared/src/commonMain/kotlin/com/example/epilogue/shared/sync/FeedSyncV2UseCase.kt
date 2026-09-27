package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.FeedMutationResultV2
import com.example.epilogue.shared.ghostwriter.isUuidV2
import com.example.epilogue.shared.ghostwriter.isValidV2
import com.example.epilogue.shared.ghostwriter.validVersionV2
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext

sealed class FeedSyncV2Outcome {
    data class Complete(val applied: Int, val pulled: Int) : FeedSyncV2Outcome()
    data class Partial(
        val applied: Int, val pulled: Int, val pending: Int,
        val conflicts: Int, val rejected: Int, val phase: String?
    ) : FeedSyncV2Outcome()
    data class Failed(val phase: String, val message: String) : FeedSyncV2Outcome()
    data object NotConfigured : FeedSyncV2Outcome()
    data object ServerUpgradeRequired : FeedSyncV2Outcome()
    data object ServerChanged : FeedSyncV2Outcome()
}

class FeedSyncV2UseCase(
    private val configuration: FeedV2ConfigurationPort,
    private val store: FeedV2StorePort,
    private val remote: FeedV2RemotePort
) {
    suspend fun sync(): FeedSyncV2Outcome {
        val destination = configuration.currentDestination() ?: return FeedSyncV2Outcome.NotConfigured
        val gate = when (val begun = store.beginSyncRun(destination)) {
            is FeedV2StoreResult.Success -> begun.value
            FeedV2StoreResult.Busy -> return FeedSyncV2Outcome.Partial(0, 0, 0, 0, 0, "busy")
            else -> return storeFailure("begin", begun)
        }
        try {
            return syncInGate(destination, gate)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            return FeedSyncV2Outcome.Failed("sync", error.message ?: "Unexpected sync failure")
        } finally {
            withContext(NonCancellable) { store.endSyncRun(gate) }
        }
    }

    private suspend fun syncInGate(
        destination: FeedV2Destination, token: FeedV2RunToken
    ): FeedSyncV2Outcome {
        var binding = when (val read = store.getServerIdentity(token)) {
            is FeedV2StoreResult.Success -> read.value
            else -> return storeFailure("binding", read)
        }
        if (binding != null && (binding.suspended || binding.destination != destination)) {
            if (!binding.suspended) {
                val suspended = store.suspendBinding(token, binding, "changed_destination")
                if (suspended !is FeedV2StoreResult.Success) return storeFailure("suspend", suspended)
            }
            return FeedSyncV2Outcome.ServerChanged
        }

        var pulled = 0
        if (binding == null || !binding.firstReconciliationComplete) {
            if (configuration.currentDestination() != destination) return FeedSyncV2Outcome.ServerChanged
            val full = when (val result = remote.getFeedChangesV2(destination, null, null)) {
                is FeedV2RemoteResult.Success -> result.value
                else -> return remoteFailure("full_pull", result, token, binding)
            }
            if (!full.isValidV2(full = true, sinceVersion = null) ||
                (binding?.serverInstanceId != null && full.serverInstanceId != binding.serverInstanceId)) {
                if (binding?.serverInstanceId != null && full.serverInstanceId != binding.serverInstanceId) {
                    val suspended = store.suspendBinding(token, binding, "changed_instance")
                    if (suspended !is FeedV2StoreResult.Success) return storeFailure("suspend", suspended)
                    return FeedSyncV2Outcome.ServerChanged
                }
                return FeedSyncV2Outcome.Failed("full_pull", "Invalid full response")
            }
            if (configuration.currentDestination() != destination) return changedDestination(token, binding)
            binding = when (val result = store.reconcileAndBindFullSnapshot(token, destination, full)) {
                is FeedV2StoreResult.Success -> result.value
                else -> return storeFailure("reconcile", result)
            }
            if (!binding.firstReconciliationComplete || binding.serverInstanceId != full.serverInstanceId ||
                binding.cursorVersion != full.serverVersion) {
                return FeedSyncV2Outcome.Failed("reconcile", "Store returned inconsistent binding")
            }
            pulled += full.changes.size
        }
        val bound = binding
        if (!isUuidV2(bound.serverInstanceId ?: "") || !validVersionV2(bound.cursorVersion ?: -1)) {
            return FeedSyncV2Outcome.Failed("binding", "Invalid binding")
        }
        if (configuration.currentDestination() != destination) return changedDestination(token, bound)

        val claimed = when (val result = store.loadPendingMutations(token, bound, 100)) {
            is FeedV2StoreResult.Success -> result.value
            else -> return storeFailure("claim", result)
        }
        if (claimed.size > 100 || claimed.map { it.url }.distinct().size != claimed.size ||
            claimed.any { it.payload.opId != it.opId || it.payload.url != it.url }) {
            return FeedSyncV2Outcome.Failed("claim", "Invalid claimed mutations")
        }
        var applied = 0
        var pushFailure: String? = null
        if (claimed.isNotEmpty()) {
            if (configuration.currentDestination() != destination) return changedDestination(token, bound)
            val batch = FeedMutationBatchV2(bound.serverInstanceId!!, claimed.map { it.payload })
            val result = remote.postFeedMutationsV2(destination, batch)
            when (result) {
                is FeedV2RemoteResult.Success -> {
                    val envelope = result.value
                    if (envelope.serverInstanceId != bound.serverInstanceId) {
                        val suspended = store.suspendBinding(token, bound, "changed_instance")
                        if (suspended !is FeedV2StoreResult.Success) return storeFailure("suspend", suspended)
                        return FeedSyncV2Outcome.ServerChanged
                    }
                    if (!validResults(envelope.results, claimed)) {
                        pushFailure = "invalid_response"
                    } else {
                        if (configuration.currentDestination() != destination) return changedDestination(token, bound)
                        val resultsById = envelope.results.associateBy { it.opId }
                        for (sent in claimed) {
                            val outcome = resultsById.getValue(sent.opId)
                            val stored = when (outcome.status) {
                                "applied" -> store.acknowledge(token, bound, sent.opId, sent.sentRevision, outcome.current)
                                "conflict" -> store.recordConflict(token, bound, sent.opId, sent.sentRevision, outcome.current!!)
                                else -> store.recordRejection(token, bound, sent.opId, sent.sentRevision,
                                    outcome.code!!, outcome.message)
                            }
                            if (stored !is FeedV2StoreResult.Success) return storeFailure("result_apply", stored)
                            if (outcome.status == "applied") applied++
                        }
                    }
                }
                else -> {
                    val failure = remoteFailure("push", result, token, bound)
                    if (failure is FeedSyncV2Outcome.ServerChanged ||
                        failure is FeedSyncV2Outcome.ServerUpgradeRequired) return failure
                    pushFailure = "push"
                }
            }
        }

        if (configuration.currentDestination() != destination) return changedDestination(token, bound)
        val changes = when (val result = remote.getFeedChangesV2(
            destination, bound.cursorVersion, bound.serverInstanceId
        )) {
            is FeedV2RemoteResult.Success -> result.value
            else -> {
                val failure = remoteFailure("pull", result, token, bound)
                if (failure is FeedSyncV2Outcome.ServerChanged ||
                    failure is FeedSyncV2Outcome.ServerUpgradeRequired) return failure
                return partialFromSummary(token, bound, applied, pulled, "pull")
            }
        }
        if (changes.serverInstanceId != bound.serverInstanceId) {
            val suspended = store.suspendBinding(token, bound, "changed_instance")
            if (suspended !is FeedV2StoreResult.Success) return storeFailure("suspend", suspended)
            return FeedSyncV2Outcome.ServerChanged
        }
        if (!changes.isValidV2(full = false, sinceVersion = bound.cursorVersion) ||
            changes.serverVersion < bound.cursorVersion!!) {
            return FeedSyncV2Outcome.Failed("pull", "Invalid incremental response")
        }
        if (configuration.currentDestination() != destination) return changedDestination(token, bound)
        val appliedPull = store.applyServerChangesAndCursor(token, bound, changes)
        if (appliedPull !is FeedV2StoreResult.Success) return storeFailure("pull_apply", appliedPull)
        pulled += changes.changes.size

        val summary = when (val result = store.pendingSummary(token, bound)) {
            is FeedV2StoreResult.Success -> result.value
            else -> return storeFailure("summary", result)
        }
        return if (pushFailure == null && summary.pending == 0) FeedSyncV2Outcome.Complete(applied, pulled)
        else FeedSyncV2Outcome.Partial(applied, pulled, summary.pending,
            summary.blockedConflicts, summary.rejected, pushFailure ?: "pending")
    }

    private fun validResults(results: List<FeedMutationResultV2>, sent: List<SentFeedMutationV2>): Boolean {
        if (results.size != sent.size) return false
        val byId = sent.associateBy { it.opId }
        if (byId.size != sent.size || results.map { it.opId }.toSet().size != results.size) return false
        return results.all { result ->
            val item = byId[result.opId] ?: return@all false
            when (result.status) {
                "applied" -> result.current?.let { current ->
                    current.isValidV2() && current.url == item.url &&
                        (item.payload.kind == "delete") == (current.kind == "tombstone")
                } ?: (item.payload.kind == "delete" && item.payload.baseVersion == null)
                "conflict" -> result.current?.let { it.isValidV2() && it.url == item.url } == true
                "rejected" -> result.current == null && !result.code.isNullOrBlank()
                else -> false
            }
        }
    }

    private suspend fun changedDestination(
        token: FeedV2RunToken, binding: FeedV2Binding?
    ): FeedSyncV2Outcome {
        if (binding != null) {
            val result = store.suspendBinding(token, binding, "changed_destination")
            if (result !is FeedV2StoreResult.Success) return storeFailure("suspend", result)
        }
        return FeedSyncV2Outcome.ServerChanged
    }

    private suspend fun remoteFailure(
        phase: String, result: FeedV2RemoteResult<*>, token: FeedV2RunToken,
        binding: FeedV2Binding?
    ): FeedSyncV2Outcome {
        if (result is FeedV2RemoteResult.HttpFailure) {
            if (result.status == 409 && result.code == "server_changed") {
                if (binding != null) {
                    val suspended = store.suspendBinding(token, binding, "changed_instance")
                    if (suspended !is FeedV2StoreResult.Success) return storeFailure("suspend", suspended)
                }
                return FeedSyncV2Outcome.ServerChanged
            }
            if (result.status == 404 || result.status == 405) return FeedSyncV2Outcome.ServerUpgradeRequired
            return FeedSyncV2Outcome.Failed(phase, "HTTP ${result.status}${result.code?.let { "/$it" } ?: ""}")
        }
        return FeedSyncV2Outcome.Failed(phase,
            (result as? FeedV2RemoteResult.TransportFailure)?.message ?: "Remote failure")
    }

    private suspend fun partialFromSummary(
        token: FeedV2RunToken, binding: FeedV2Binding, applied: Int, pulled: Int, phase: String
    ): FeedSyncV2Outcome {
        return when (val summary = store.pendingSummary(token, binding)) {
            is FeedV2StoreResult.Success -> FeedSyncV2Outcome.Partial(applied, pulled,
                summary.value.pending, summary.value.blockedConflicts, summary.value.rejected, phase)
            else -> storeFailure("summary", summary)
        }
    }

    private fun storeFailure(phase: String, result: FeedV2StoreResult<*>): FeedSyncV2Outcome =
        FeedSyncV2Outcome.Failed(phase, when (result) {
            is FeedV2StoreResult.Failure -> result.message
            FeedV2StoreResult.Busy -> "Sync already running"
            FeedV2StoreResult.StaleBinding -> "Stale binding"
            FeedV2StoreResult.StaleSentRevision -> "Stale sent revision"
            is FeedV2StoreResult.Success -> "Unexpected store state"
        })
}
