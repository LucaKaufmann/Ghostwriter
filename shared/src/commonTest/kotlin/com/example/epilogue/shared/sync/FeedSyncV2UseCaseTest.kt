package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedDirtyFieldsV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.FeedMutationResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationV2
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.ghostwriter.toWireJson
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.CancellationException
import kotlin.test.assertFailsWith

class FeedSyncV2UseCaseTest {
    private val instance = "21410e08-44a1-4944-8910-5a74c39a7271"
    private val id = "2df6a71e-2db3-428b-8372-058794b8df35"
    private val op = "3e1a59a5-f547-40b2-9a6b-4c54e80a03dc"
    private val url = "https://example.test/rss"
    private val destination = FeedV2Destination("http://localhost:8080", "config-1")
    private fun feed(version: Long) = FeedSnapshotV2("feed", id, url, version, "Web", true, "raw", 0)
    private fun full(vararg rows: FeedSnapshotV2) = FeedChangesV2Response(instance,
        rows.maxOfOrNull { it.version } ?: 0, rows.toList())
    private fun sent(kind: String = "upsert", base: Long? = 4) = SentFeedMutationV2(
        op, url, 1, 1, FeedMutationV2(op, url, kind, base,
            if (kind == "upsert") FeedDirtyFieldsV2(title = "Local") else null))

    @Test
    fun firstPullPrecedesClaimAndOnlyCompleteSnapshotBinds() = runTest {
        val store = FakeStore()
        val remote = FakeRemote().apply { fullResponse = full(feed(4)) }
        val outcome = useCase(store, remote).sync()
        assertIs<FeedSyncV2Outcome.Complete>(outcome)
        assertEquals(listOf("full", "incremental"), remote.events)
        assertEquals(4, store.binding?.cursorVersion)
        assertEquals(1, store.reconciliations)
        assertEquals(0, store.claims.size)
        val brokenStore = FakeStore()
        val broken = FakeRemote().apply { fullResponse = full(feed(4).copy(title = null)) }
        assertIs<FeedSyncV2Outcome.Failed>(useCase(brokenStore, broken).sync())
        assertEquals(null, brokenStore.binding)
    }

    @Test
    fun malformedWholeBatchKeepsEveryOpAndPullStillRuns() = runTest {
        val store = FakeStore(bound = true).apply { claims += sent() }
        val remote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "applied", feed(5)),
                FeedMutationResultV2(op, "applied", feed(5)))
        }
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals("invalid_response", outcome.phase)
        assertEquals(1, outcome.pending)
        assertTrue(store.acks.isEmpty())
        assertEquals(1, store.pullApplies)
    }

    @Test
    fun reorderedResultsMapByOpIdAndExactRevision() = runTest {
        val secondOp = "a61d59d1-d936-4cfb-a20e-97718ddb0ff2"
        val secondUrl = "https://example.test/other"
        val second = SentFeedMutationV2(secondOp, secondUrl, 2, 8,
            FeedMutationV2(secondOp, secondUrl, "delete", 4))
        val store = FakeStore(bound = true).apply { claims.addAll(listOf(sent(), second)) }
        val remote = FakeRemote().apply {
            pushResults = listOf(
                FeedMutationResultV2(secondOp, "applied", FeedSnapshotV2("tombstone", id, secondUrl, 6)),
                FeedMutationResultV2(op, "applied", feed(5)))
        }
        assertIs<FeedSyncV2Outcome.Complete>(useCase(store, remote).sync())
        assertEquals(listOf(op to 1L, secondOp to 8L), store.acks)
    }

    @Test
    fun failedPushThenGoodPullIsPartialAndRetainsClaim() = runTest {
        val store = FakeStore(bound = true).apply { claims += sent() }
        val remote = FakeRemote().apply { pushFailure = FeedV2RemoteResult.TransportFailure("timeout") }
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals("push", outcome.phase)
        assertEquals(1, outcome.pending)
        assertTrue(store.acks.isEmpty())
        assertEquals(1, store.pullApplies)
    }

    @Test
    fun changedInstanceOn200Or409SuspendsBeforeApplying() = runTest {
        val replacement = "32d9e893-af40-40a5-8bbb-1baf97dd7f85"
        for (onPush in listOf(false, true)) {
            val store = FakeStore(bound = true).apply { if (onPush) claims += sent() }
            val remote = FakeRemote().apply {
                if (onPush) pushInstance = replacement else incrementalResponse =
                    FeedChangesV2Response(replacement, 4, emptyList())
            }
            assertIs<FeedSyncV2Outcome.ServerChanged>(useCase(store, remote).sync())
            assertTrue(store.suspended)
            assertEquals(0, store.pullApplies)
            assertTrue(store.acks.isEmpty())
        }
        val store = FakeStore(bound = true)
        val remote = FakeRemote().apply { pullFailure = FeedV2RemoteResult.HttpFailure(409, "server_changed") }
        assertIs<FeedSyncV2Outcome.ServerChanged>(useCase(store, remote).sync())
        assertTrue(store.suspended)
    }

    @Test
    fun rejectionBlocksAndPullFailureCannotAdvanceCursor() = runTest {
        val store = FakeStore(bound = true).apply { claims += sent() }
        val remote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "rejected", code = "invalid_fields", message = "Bad"))
        }
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(1, outcome.rejected)
        assertEquals(listOf(op), store.rejections)
        assertEquals(4, store.binding?.cursorVersion)
        val failedStore = FakeStore(bound = true).apply { failPullApply = true }
        assertIs<FeedSyncV2Outcome.Failed>(useCase(failedStore, FakeRemote()).sync())
        assertEquals(4, failedStore.binding?.cursorVersion)
    }

    @Test
    fun mismatchedResultUrlOrKindPreventsEveryAcknowledgement() = runTest {
        for (current in listOf(
            feed(5).copy(url = "https://example.test/wrong"),
            FeedSnapshotV2("tombstone", id, url, 5),
            feed(9_007_199_254_740_992L)
        )) {
            val store = FakeStore(bound = true).apply { claims += sent() }
            val remote = FakeRemote().apply {
                pushResults = listOf(FeedMutationResultV2(op, "applied", current))
            }
            assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
            assertTrue(store.acks.isEmpty())
            assertEquals(1, store.claims.size)
        }
    }

    @Test
    fun cancellationReleasesGateWithoutAcknowledgement() = runTest {
        val store = FakeStore(bound = true)
        val remote = FakeRemote().apply { cancelPull = true }
        assertFailsWith<CancellationException> { useCase(store, remote).sync() }
        assertEquals(1, store.endCalls)
        assertTrue(store.acks.isEmpty())
    }

    @Test
    fun oldServerRequiresUpgradeAndNeverClaims() = runTest {
        val store = FakeStore()
        val remote = FakeRemote().apply { fullFailure = FeedV2RemoteResult.HttpFailure(404, null) }
        assertIs<FeedSyncV2Outcome.ServerUpgradeRequired>(useCase(store, remote).sync())
        assertEquals(null, store.binding)
        assertEquals(0, store.loadCalls)
    }

    @Test
    fun localOnlyDoesNotTouchOutboxAndDestinationSwitchSuspends() = runTest {
        val store = FakeStore(bound = true).apply { claims += sent() }
        val remote = FakeRemote()
        assertIs<FeedSyncV2Outcome.NotConfigured>(useCase(store, remote, null).sync())
        assertEquals(0, store.loadCalls)
        val switched = destination.copy(configurationId = "config-2")
        assertIs<FeedSyncV2Outcome.ServerChanged>(useCase(store, remote, switched).sync())
        assertTrue(store.suspended)
        assertTrue(remote.events.isEmpty())
        assertEquals(1, store.claims.size)
    }

    @Test
    fun timeoutReplaysSamePayloadAndSuccessorWaitsForExactHeadAck() = runTest {
        val successorId = "a61d59d1-d936-4cfb-a20e-97718ddb0ff2"
        val store = FakeStore(bound = true).apply {
            claims += sent()
            successors += SentFeedMutationV2(successorId, url, 2, 2,
                FeedMutationV2(successorId, url, "upsert", 4,
                    FeedDirtyFieldsV2(maxArticles = 0)))
        }
        val remote = FakeRemote().apply { pushFailure = FeedV2RemoteResult.TransportFailure("timeout") }
        val first = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(2, first.pending)
        assertEquals(listOf(op), remote.sentBatches.single().mutations.map { it.opId })
        remote.pushFailure = null
        val second = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(remote.sentBatches[0], remote.sentBatches[1])
        assertEquals(listOf(op to 1L), store.acks)
        assertEquals(successorId, store.claims.single().opId)
        assertEquals(5, store.claims.single().payload.baseVersion)
        assertEquals(1, second.pending)
        assertIs<FeedSyncV2Outcome.Complete>(useCase(store, remote).sync())
        assertEquals(listOf(op to 1L, successorId to 2L), store.acks)
    }

    @Test
    fun deleteThenReaddWaitsAndUsesTombstoneBaseAndStableId() = runTest {
        val readdId = "a61d59d1-d936-4cfb-a20e-97718ddb0ff2"
        val store = FakeStore(bound = true).apply {
            claims += sent("delete")
            successors += SentFeedMutationV2(readdId, url, 2, 2,
                FeedMutationV2(readdId, url, "upsert", null,
                    FeedDirtyFieldsV2("Readd", true, "raw", 0)))
        }
        val remote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "applied",
                FeedSnapshotV2("tombstone", id, url, 5)))
        }
        assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(listOf(op), remote.sentBatches.single().mutations.map { it.opId })
        assertEquals(5, store.claims.single().payload.baseVersion)
        assertEquals(id, store.serverSnapshots[url]?.id)
        remote.pushResults = null
        assertIs<FeedSyncV2Outcome.Complete>(useCase(store, remote).sync())
        assertEquals(readdId, remote.sentBatches.last().mutations.single().opId)
    }

    @Test
    fun olderReceiptDoesNotRollBackNewerPulledSnapshot() = runTest {
        val store = FakeStore(bound = true).apply {
            claims += sent()
            serverSnapshots[url] = feed(9)
            successors += SentFeedMutationV2("a61d59d1-d936-4cfb-a20e-97718ddb0ff2",
                url, 2, 2, FeedMutationV2("a61d59d1-d936-4cfb-a20e-97718ddb0ff2",
                    url, "upsert", 4, FeedDirtyFieldsV2(title = "Later")))
        }
        val remote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "applied", feed(5)))
            incrementalResponse = FeedChangesV2Response(instance, 9, emptyList())
        }
        assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(9, store.serverSnapshots[url]?.version)
        assertEquals(listOf(op to 1L), store.acks)
        assertEquals(1, store.successors.size)
        assertEquals(0, store.claims.size)
        assertEquals(1, store.needsResolution)
    }

    @Test
    fun conflictRetainsProposalAndBlocksSameUrlSuccessor() = runTest {
        val store = FakeStore(bound = true).apply {
            claims += sent()
            successors += SentFeedMutationV2("a61d59d1-d936-4cfb-a20e-97718ddb0ff2",
                url, 2, 2, FeedMutationV2("a61d59d1-d936-4cfb-a20e-97718ddb0ff2",
                    url, "upsert", 4, FeedDirtyFieldsV2(title = "Later")))
        }
        val remote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "conflict", feed(5)))
        }
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(1, outcome.conflicts)
        assertEquals(2, outcome.pending)
        assertEquals(op, store.blockedHeads.single().opId)
        assertEquals(1, store.successors.size)
        assertTrue(store.acks.isEmpty())
        useCase(store, remote).sync()
        assertEquals(1, remote.sentBatches.size)
    }

    @Test
    fun batchStopsAt100AndRemainingWorkMakesPartial() = runTest {
        val store = FakeStore(bound = true)
        repeat(101) { n ->
            val uniqueOp = "00000000-0000-4000-8000-${n.toString(16).padStart(12, '0')}"
            val uniqueUrl = "https://example.test/$n"
            store.claims += SentFeedMutationV2(uniqueOp, uniqueUrl, n.toLong(), 1,
                FeedMutationV2(uniqueOp, uniqueUrl, "upsert", 4,
                    FeedDirtyFieldsV2(title = "Local")))
        }
        val remote = FakeRemote()
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(100, remote.sentBatches.single().mutations.size)
        assertEquals(100, outcome.applied)
        assertEquals(1, outcome.pending)
    }

    @Test
    fun typedClaimFailureCannotLookLikeEmptyQueue() = runTest {
        val store = FakeStore(bound = true).apply { failLoad = true }
        val outcome = assertIs<FeedSyncV2Outcome.Failed>(useCase(store, FakeRemote()).sync())
        assertEquals("claim", outcome.phase)
    }

    @Test
    fun uppercaseSentOpAcceptsCanonicalReceiptAndReplaysOriginalPayload() = runTest {
        val upper = sent().copy(opId = op.uppercase(),
            payload = sent().payload.copy(opId = op.uppercase()))
        val store = FakeStore(bound = true).apply { claims += upper }
        val remote = FakeRemote().apply { pushFailure = FeedV2RemoteResult.TransportFailure("timeout") }
        assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(op.uppercase(), remote.sentBatches.single().mutations.single().opId)
        remote.pushFailure = null
        remote.pushResults = listOf(FeedMutationResultV2(op, "applied", feed(5)))
        assertIs<FeedSyncV2Outcome.Complete>(useCase(store, remote).sync())
        assertEquals(remote.sentBatches[0].toWireJson(), remote.sentBatches[1].toWireJson())
        assertEquals(listOf(op.uppercase() to 1L), store.acks)
    }

    @Test
    fun caseVariantClaimOrResultDuplicatesNeverAcknowledge() = runTest {
        val secondUrl = "https://example.test/other"
        val second = SentFeedMutationV2(op.uppercase(), secondUrl, 2, 2,
            FeedMutationV2(op.uppercase(), secondUrl, "delete", 4))
        val duplicateClaims = FakeStore(bound = true).apply { claims.addAll(listOf(sent(), second)) }
        val remote = FakeRemote()
        assertIs<FeedSyncV2Outcome.Failed>(useCase(duplicateClaims, remote).sync())
        assertTrue(remote.sentBatches.isEmpty())
        assertTrue(duplicateClaims.acks.isEmpty())

        val otherId = "a61d59d1-d936-4cfb-a20e-97718ddb0ff2"
        val distinctSecond = second.copy(opId = otherId,
            payload = second.payload.copy(opId = otherId))
        val resultStore = FakeStore(bound = true).apply { claims.addAll(listOf(sent(), distinctSecond)) }
        val resultRemote = FakeRemote().apply {
            pushResults = listOf(FeedMutationResultV2(op, "applied", feed(5)),
                FeedMutationResultV2(op.uppercase(), "applied", feed(5)))
        }
        assertIs<FeedSyncV2Outcome.Partial>(useCase(resultStore, resultRemote).sync())
        assertTrue(resultStore.acks.isEmpty())
        assertEquals(2, resultStore.claims.size)
    }

    @Test
    fun uppercaseInstanceIsSameServerOnPushAndPull() = runTest {
        val store = FakeStore(bound = true).apply { claims += sent() }
        val remote = FakeRemote().apply {
            pushInstance = instance.uppercase()
            incrementalResponse = FeedChangesV2Response(instance.uppercase(), 4, emptyList())
        }
        assertIs<FeedSyncV2Outcome.Complete>(useCase(store, remote).sync())
        assertEquals(listOf(op to 1L), store.acks)
        assertTrue(!store.suspended)
    }

    @Test
    fun firstReconcileKeepsMismatchTombstoneAndAbsenceAsResolution() = runTest {
        val tombstoneUrl = "https://example.test/deleted"
        val absentUrl = "https://example.test/absent"
        val differentUrl = "https://example.test/different"
        val store = FakeStore().apply {
            // This fake deliberately ignores the legacy dirty flag: all old rows carry proposals.
            legacyRows[url] = FeedDirtyFieldsV2("Web", true, "raw", 0)
            legacyRows[tombstoneUrl] = FeedDirtyFieldsV2("Local", true, "raw", 0)
            legacyRows[absentUrl] = FeedDirtyFieldsV2("Local", true, "raw", 0)
            legacyRows[differentUrl] = FeedDirtyFieldsV2("Local", true, "raw", 0)
            legacyRows["synthetic://internal"] = FeedDirtyFieldsV2("Internal", true, "raw", 0)
        }
        val remote = FakeRemote().apply {
            fullResponse = full(feed(4), FeedSnapshotV2("tombstone", id, tombstoneUrl, 5),
                feed(6).copy(url = differentUrl))
            incrementalResponse = FeedChangesV2Response(instance, 6, emptyList())
        }
        val outcome = assertIs<FeedSyncV2Outcome.Partial>(useCase(store, remote).sync())
        assertEquals(3, outcome.pending)
        assertEquals(3, store.needsResolution)
        assertEquals(6, store.binding?.cursorVersion)
        assertEquals(0, remote.sentBatches.size)
    }

    private fun useCase(store: FakeStore, remote: FakeRemote,
        configured: FeedV2Destination? = destination) = FeedSyncV2UseCase(
        object : FeedV2ConfigurationPort {
            override suspend fun currentDestination() = configured
        }, store, remote)

    private inner class FakeRemote : FeedV2RemotePort {
        var fullResponse = full()
        var incrementalResponse = FeedChangesV2Response(instance, 4, emptyList())
        var pushInstance = instance
        var pushResults: List<FeedMutationResultV2>? = null
        var pushFailure: FeedV2RemoteResult<FeedMutationBatchResultV2>? = null
        var pullFailure: FeedV2RemoteResult<FeedChangesV2Response>? = null
        var fullFailure: FeedV2RemoteResult<FeedChangesV2Response>? = null
        var cancelPull = false
        val events = mutableListOf<String>()
        val sentBatches = mutableListOf<FeedMutationBatchV2>()
        override suspend fun getFeedChangesV2(
            destination: FeedV2Destination, sinceVersion: Long?, serverInstanceId: String?
        ): FeedV2RemoteResult<FeedChangesV2Response> {
            events += if (sinceVersion == null) "full" else "incremental"
            if (cancelPull) throw CancellationException("cancel")
            return if (sinceVersion == null) fullFailure ?: FeedV2RemoteResult.Success(fullResponse)
            else pullFailure ?: FeedV2RemoteResult.Success(incrementalResponse.copy(
                serverVersion = maxOf(incrementalResponse.serverVersion, sinceVersion)))
        }
        override suspend fun postFeedMutationsV2(
            destination: FeedV2Destination, batch: FeedMutationBatchV2
        ): FeedV2RemoteResult<FeedMutationBatchResultV2> {
            events += "push"
            sentBatches += batch
            return pushFailure ?: FeedV2RemoteResult.Success(FeedMutationBatchResultV2(pushInstance,
                pushResults ?: batch.mutations.map { item -> FeedMutationResultV2(item.opId, "applied",
                    feed(5).copy(url = item.url)) }))
        }
    }

    private inner class FakeStore(bound: Boolean = false) : FeedV2StorePort {
        var binding: FeedV2Binding? = if (bound) FeedV2Binding(destination, instance, 4, true, 1) else null
        val claims = mutableListOf<SentFeedMutationV2>()
        val successors = mutableListOf<SentFeedMutationV2>()
        val blockedHeads = mutableListOf<SentFeedMutationV2>()
        val serverSnapshots = mutableMapOf<String, FeedSnapshotV2>()
        val legacyRows = mutableMapOf<String, FeedDirtyFieldsV2>()
        var needsResolution = 0
        val acks = mutableListOf<Pair<String, Long>>()
        val rejections = mutableListOf<String>()
        var suspended = false
        var reconciliations = 0
        var pullApplies = 0
        var failPullApply = false
        var endCalls = 0
        var loadCalls = 0
        var failLoad = false
        override suspend fun beginSyncRun(destination: FeedV2Destination) =
            FeedV2StoreResult.Success(FeedV2RunToken("token"))
        override suspend fun endSyncRun(token: FeedV2RunToken) { endCalls++ }
        override suspend fun getServerIdentity(token: FeedV2RunToken) = FeedV2StoreResult.Success(binding)
        override suspend fun suspendBinding(token: FeedV2RunToken, binding: FeedV2Binding, reason: String): FeedV2StoreResult<Unit> {
            suspended = true
            this.binding = binding.copy(suspended = true, generation = binding.generation + 1)
            return FeedV2StoreResult.Success(Unit)
        }
        override suspend fun reconcileAndBindFullSnapshot(token: FeedV2RunToken,
            destination: FeedV2Destination, snapshot: FeedChangesV2Response): FeedV2StoreResult<FeedV2Binding> {
            reconciliations++
            val remoteByUrl = snapshot.changes.associateBy { it.url }
            needsResolution = legacyRows.count { (url, proposal) ->
                if (url.startsWith("synthetic://")) return@count false
                val current = remoteByUrl[url]
                current == null || current.kind != "feed" || proposal != FeedDirtyFieldsV2(
                    current.title, current.isActive, current.mode, current.maxArticles)
            }
            snapshot.changes.forEach { serverSnapshots[it.url] = it }
            val value = FeedV2Binding(destination, snapshot.serverInstanceId, snapshot.serverVersion, true, 1)
            binding = value
            return FeedV2StoreResult.Success(value)
        }
        override suspend fun loadPendingMutations(token: FeedV2RunToken,
            binding: FeedV2Binding, maxItems: Int): FeedV2StoreResult<List<SentFeedMutationV2>> {
            loadCalls++
            if (failLoad) return FeedV2StoreResult.Failure("claim failed")
            return FeedV2StoreResult.Success(claims.take(maxItems))
        }
        override suspend fun pendingSummary(token: FeedV2RunToken,
            binding: FeedV2Binding): FeedV2StoreResult<FeedV2WorkSummary> =
            FeedV2StoreResult.Success(FeedV2WorkSummary(claims.size, blockedHeads.size, rejections.size,
                successors.size, needsResolution))
        override suspend fun acknowledge(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, current: FeedSnapshotV2?): FeedV2StoreResult<Unit> {
            acks += opId to sentRevision
            val head = claims.single { it.opId == opId && it.sentRevision == sentRevision }
            claims.remove(head)
            val previouslyObserved = serverSnapshots[head.url]
            val olderReceipt = current != null && previouslyObserved != null &&
                current.version < previouslyObserved.version
            if (current != null && !olderReceipt) {
                serverSnapshots[current.url] = current
            }
            val successor = successors.firstOrNull { it.url == head.url }
            if (successor != null && olderReceipt) {
                needsResolution++
            } else if (successor != null) {
                successors.remove(successor)
                val latest = serverSnapshots[head.url]
                claims += successor.copy(payload = successor.payload.copy(baseVersion = latest?.version))
            }
            return FeedV2StoreResult.Success(Unit)
        }
        override suspend fun recordConflict(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, current: FeedSnapshotV2): FeedV2StoreResult<Unit> {
            val head = claims.single { it.opId == opId && it.sentRevision == sentRevision }
            claims.remove(head)
            blockedHeads += head
            if ((serverSnapshots[current.url]?.version ?: -1) <= current.version) {
                serverSnapshots[current.url] = current
            }
            return FeedV2StoreResult.Success(Unit)
        }
        override suspend fun recordRejection(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, code: String, message: String?): FeedV2StoreResult<Unit> {
            rejections += opId
            claims.removeAll { it.opId == opId }
            return FeedV2StoreResult.Success(Unit)
        }
        override suspend fun applyServerChangesAndCursor(token: FeedV2RunToken,
            binding: FeedV2Binding, changes: FeedChangesV2Response): FeedV2StoreResult<Unit> {
            if (failPullApply) return FeedV2StoreResult.Failure("disk failure")
            pullApplies++
            this.binding = binding.copy(cursorVersion = changes.serverVersion)
            return FeedV2StoreResult.Success(Unit)
        }
    }
}
