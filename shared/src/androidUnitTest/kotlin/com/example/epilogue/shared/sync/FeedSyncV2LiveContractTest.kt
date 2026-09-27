package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedDirtyFieldsV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationV2
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.ghostwriter.GhostwriterClientHandle
import java.net.URI
import java.util.UUID
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking
import org.junit.Assume.assumeTrue

/** Opt-in real OkHttp -> FastAPI -> SQLite protocol check. Native stores have separate tests. */
class FeedSyncV2LiveContractTest {
    @Test
    fun realServerHonorsVersionedMutationAndDeleteContract() = runBlocking {
        val baseUrl = System.getenv("FEED_SYNC_LIVE_URL") ?: ""
        assumeTrue("Live fixture is opt-in", baseUrl.isNotBlank())
        val uri = URI(baseUrl)
        require(uri.scheme == "http" && uri.host == "127.0.0.1" && uri.port in 1..65535 &&
            uri.rawUserInfo == null && (uri.rawPath.isNullOrEmpty() || uri.rawPath == "/") &&
            uri.rawQuery == null && uri.rawFragment == null) {
            "Live fixture must be disposable loopback HTTP"
        }
        val destination = FeedV2Destination(baseUrl, "live-test")
        val feedUrl = "$baseUrl/fixture-article?feed-sync-live=1"
        val handleA = GhostwriterClientHandle.create(baseUrl, null)
        val handleB = GhostwriterClientHandle.create(baseUrl, null)
        try {
            val clientA = handleA.client
            val clientB = handleB.client
            val initial = success(clientA.getFeedChangesV2(destination, null, null))
            val instance = initial.serverInstanceId
            assertTrue(initial.changes.none { it.url == feedUrl })
            assertEquals(instance, success(clientB.getFeedChangesV2(destination, null, null)).serverInstanceId)

            // Swift UUID.uuidString is uppercase. The server returns a lowercase receipt ID.
            val uppercaseOp = UUID.randomUUID().toString().uppercase()
            val create = FeedMutationV2(uppercaseOp, feedUrl, "upsert", null,
                FeedDirtyFieldsV2("Local zero cap", true, "raw", 0))
            val sent = SentFeedMutationV2(uppercaseOp, feedUrl, 1, 1, create)
            val store = SingleIntentStore(sent)
            val outcome = FeedSyncV2UseCase(
                object : FeedV2ConfigurationPort {
                    override suspend fun currentDestination() = destination
                }, store, clientA
            ).sync()
            assertIs<FeedSyncV2Outcome.Complete>(outcome)
            assertEquals(uppercaseOp, store.acknowledgedOpId)
            assertEquals(1L, store.acknowledgedRevision)
            assertEquals(1, store.gateReleases)
            val created = assertNotNull(store.acknowledgedSnapshot)
            assertEquals("feed", created.kind)
            assertEquals(0, created.maxArticles)
            assertTrue(created.version > initial.serverVersion)

            // Replay the exact frozen DTO. Rewriting the UUID case changes the server's
            // payload hash and is therefore not a valid timeout replay.
            val originalBatch = FeedMutationBatchV2(instance, listOf(create))
            val replay = success(clientA.postFeedMutationsV2(destination, originalBatch))
            assertEquals(uppercaseOp.lowercase(), replay.results.single().opId)
            assertEquals("applied", replay.results.single().status)
            assertEquals(created.version, replay.results.single().current?.version)
            val afterReplay = success(clientA.getFeedChangesV2(destination, created.version, instance))
            assertEquals(created.version, afterReplay.serverVersion)
            assertTrue(afterReplay.changes.isEmpty())

            val clientBBase = success(clientB.getFeedChangesV2(destination, initial.serverVersion, instance))
                .changes.single { it.url == feedUrl }
            assertEquals(created.version, clientBBase.version)
            val updateA = mutate(clientA, destination, instance,
                FeedMutationV2(UUID.randomUUID().toString(), feedUrl, "upsert", created.version,
                    FeedDirtyFieldsV2(title = "Web-side title")))
            assertEquals("applied", updateA.status)
            val updated = assertNotNull(updateA.current)
            assertTrue(updated.version > created.version)
            val staleB = mutate(clientB, destination, instance,
                FeedMutationV2(UUID.randomUUID().toString(), feedUrl, "upsert", clientBBase.version,
                    FeedDirtyFieldsV2(mode = "summarize")))
            assertEquals("conflict", staleB.status)
            assertEquals(updated.version, staleB.current?.version)
            assertEquals("Web-side title", staleB.current?.title)
            assertEquals("raw", staleB.current?.mode)

            val deleted = mutate(clientA, destination, instance,
                FeedMutationV2(UUID.randomUUID().toString(), feedUrl, "delete", updated.version))
            assertEquals("applied", deleted.status)
            val tombstone = assertNotNull(deleted.current)
            assertEquals("tombstone", tombstone.kind)
            assertEquals(created.id, tombstone.id)
            assertTrue(tombstone.version > updated.version)
            val increment = success(clientB.getFeedChangesV2(destination, updated.version, instance))
            assertEquals(listOf(tombstone), increment.changes)
            assertEquals(tombstone.version, increment.serverVersion)

            val readded = mutate(clientB, destination, instance,
                FeedMutationV2(UUID.randomUUID().toString(), feedUrl, "upsert", tombstone.version,
                    FeedDirtyFieldsV2("Re-added", true, "raw", 0)))
            assertEquals("applied", readded.status)
            val restored = assertNotNull(readded.current)
            assertEquals("feed", restored.kind)
            assertEquals(created.id, restored.id)
            assertEquals(0, restored.maxArticles)
            assertTrue(restored.version > tombstone.version)
            assertEquals(listOf(restored), success(clientA.getFeedChangesV2(
                destination, tombstone.version, instance)).changes)

            val wrongInstance = UUID.randomUUID().toString()
            val wrongPull = clientB.getFeedChangesV2(destination, restored.version, wrongInstance)
            assertEquals("server_changed", assertIs<FeedV2RemoteResult.HttpFailure>(wrongPull).code)
            val wrongWrite = clientB.postFeedMutationsV2(destination, FeedMutationBatchV2(
                wrongInstance, listOf(FeedMutationV2(UUID.randomUUID().toString(), feedUrl,
                    "delete", restored.version))))
            assertEquals("server_changed", assertIs<FeedV2RemoteResult.HttpFailure>(wrongWrite).code)
            val unchanged = success(clientA.getFeedChangesV2(destination, restored.version, instance))
            assertEquals(restored.version, unchanged.serverVersion)
            assertTrue(unchanged.changes.isEmpty())
        } finally {
            handleB.close()
            handleA.close()
        }
    }

    private suspend fun mutate(
        client: com.example.epilogue.shared.ghostwriter.GhostwriterApiClient,
        destination: FeedV2Destination, instance: String, mutation: FeedMutationV2
    ) = success(client.postFeedMutationsV2(destination,
        FeedMutationBatchV2(instance, listOf(mutation)))).results.single()

    private fun <T> success(result: FeedV2RemoteResult<T>): T =
        assertIs<FeedV2RemoteResult.Success<T>>(result).value

    private class SingleIntentStore(private var pending: SentFeedMutationV2?) : FeedV2StorePort {
        private var binding: FeedV2Binding? = null
        var acknowledgedOpId: String? = null
        var acknowledgedRevision: Long? = null
        var acknowledgedSnapshot: FeedSnapshotV2? = null
        var gateReleases = 0
        override suspend fun beginSyncRun(destination: FeedV2Destination) =
            FeedV2StoreResult.Success(FeedV2RunToken("single-run"))
        override suspend fun endSyncRun(token: FeedV2RunToken) { gateReleases++ }
        override suspend fun getServerIdentity(token: FeedV2RunToken) = FeedV2StoreResult.Success(binding)
        override suspend fun suspendBinding(token: FeedV2RunToken, binding: FeedV2Binding,
            reason: String): FeedV2StoreResult<Unit> = error("Unexpected binding suspension: $reason")
        override suspend fun reconcileAndBindFullSnapshot(token: FeedV2RunToken,
            destination: FeedV2Destination, snapshot: FeedChangesV2Response): FeedV2StoreResult<FeedV2Binding> {
            val next = FeedV2Binding(destination, snapshot.serverInstanceId,
                snapshot.serverVersion, true, 1)
            binding = next
            return FeedV2StoreResult.Success(next)
        }
        override suspend fun loadPendingMutations(token: FeedV2RunToken,
            binding: FeedV2Binding, maxItems: Int) = FeedV2StoreResult.Success(listOfNotNull(pending))
        override suspend fun pendingSummary(token: FeedV2RunToken,
            binding: FeedV2Binding) = FeedV2StoreResult.Success(FeedV2WorkSummary(
                if (pending == null) 0 else 1, 0, 0, 0, 0))
        override suspend fun acknowledge(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, current: FeedSnapshotV2?): FeedV2StoreResult<Unit> {
            check(pending?.opId == opId && pending?.sentRevision == sentRevision)
            acknowledgedOpId = opId
            acknowledgedRevision = sentRevision
            acknowledgedSnapshot = current
            pending = null
            return FeedV2StoreResult.Success(Unit)
        }
        override suspend fun recordConflict(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, current: FeedSnapshotV2): FeedV2StoreResult<Unit> =
            error("Unexpected conflict")
        override suspend fun recordRejection(token: FeedV2RunToken, binding: FeedV2Binding,
            opId: String, sentRevision: Long, code: String, message: String?): FeedV2StoreResult<Unit> =
            error("Unexpected rejection: $code")
        override suspend fun applyServerChangesAndCursor(token: FeedV2RunToken,
            binding: FeedV2Binding, changes: FeedChangesV2Response): FeedV2StoreResult<Unit> {
            this.binding = binding.copy(cursorVersion = changes.serverVersion)
            return FeedV2StoreResult.Success(Unit)
        }
    }
}
