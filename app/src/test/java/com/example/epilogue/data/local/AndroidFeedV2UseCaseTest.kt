package com.example.epilogue.data.local

import androidx.room.Room
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.FeedMutationResultV2
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.sync.FeedV2Destination
import com.example.epilogue.shared.sync.FeedV2RemotePort
import com.example.epilogue.shared.sync.FeedV2RemoteResult
import com.example.epilogue.shared.sync.FeedV2StoreResult
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class AndroidFeedV2UseCaseTest {
    @get:Rule val files = TemporaryFolder()
    private val context get() = RuntimeEnvironment.getApplication()
    private val name get() = "feed-v2-use-case-${files.root.name}.db"
    private val serverId = "11111111-1111-4111-8111-111111111111"
    private val feedId = "22222222-2222-4222-8222-222222222222"
    private val url = "https://example.org/feed"
    private fun database() = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
        .allowMainThreadQueries().build()
    private val settings = mockk<SettingsRepository> {
        every { isGhostwriterConfigured() } returns true
        every { getGhostwriterUrl() } returns "https://fixture.invalid"
    }
    private fun feed(title: String) = Feed(url, title, ProcessingMode.FIDELITY, maxArticles = 0)
    private fun snapshot(title: String, version: Long) = FeedSnapshotV2(
        "feed", feedId, url, version, title, true, "raw", 0
    )
    private class Remote : FeedV2RemotePort {
        lateinit var pull: (Long?) -> FeedV2RemoteResult<FeedChangesV2Response>
        lateinit var push: (FeedMutationBatchV2) -> FeedV2RemoteResult<FeedMutationBatchResultV2>
        val batches = mutableListOf<FeedMutationBatchV2>()
        override suspend fun getFeedChangesV2(destination: FeedV2Destination, sinceVersion: Long?,
            serverInstanceId: String?): FeedV2RemoteResult<FeedChangesV2Response> = pull(sinceVersion)
        override suspend fun postFeedMutationsV2(destination: FeedV2Destination,
            batch: FeedMutationBatchV2): FeedV2RemoteResult<FeedMutationBatchResultV2> {
            batches += batch
            return push(batch)
        }
    }
    private suspend fun bound(store: AndroidFeedV2Store, snapshot: FeedSnapshotV2) {
        val destination = store.currentDestination()!!
        val token = (store.beginSyncRun(destination) as FeedV2StoreResult.Success).value
        assertTrue(store.reconcileAndBindFullSnapshot(token, destination,
            FeedChangesV2Response(serverId, snapshot.version, listOf(snapshot))) is FeedV2StoreResult.Success)
        store.endSyncRun(token)
    }

    @Test fun `real Room store and shared use case create ack and pull complete`() = runBlocking {
        context.deleteDatabase(name)
        val db = database()
        val store = AndroidFeedV2Store(db, settings)
        store.saveLocal(feed("Created"))
        val remote = Remote().apply {
            pull = { since -> FeedV2RemoteResult.Success(if (since == null)
                FeedChangesV2Response(serverId, 0, emptyList())
                else FeedChangesV2Response(serverId, 1, listOf(snapshot("Created", 1)))) }
            push = { batch -> FeedV2RemoteResult.Success(FeedMutationBatchResultV2(serverId,
                listOf(FeedMutationResultV2(batch.mutations.single().opId, "applied", snapshot("Created", 1))))) }
        }
        val result = FeedSyncV2UseCase(store, store, remote).sync()
        assertTrue(result is FeedSyncV2Outcome.Complete)
        assertEquals(1, remote.batches.size)
        assertEquals(0, remote.batches.single().mutations.single().fields!!.maxArticles)
        assertTrue(db.feedMutationDao().forUrl(url).isEmpty())
        assertEquals(1L, db.feedDao().getFeedByUrl(url)!!.serverVersion)
        db.close()
    }

    @Test fun `shared use case retains local proposal after conflict`() = runBlocking {
        context.deleteDatabase(name)
        val db = database()
        val store = AndroidFeedV2Store(db, settings)
        bound(store, snapshot("Server old", 4))
        store.saveLocal(feed("Mine"))
        val remote = Remote().apply {
            pull = { FeedV2RemoteResult.Success(FeedChangesV2Response(serverId, 5, listOf(snapshot("Web", 5)))) }
            push = { batch -> FeedV2RemoteResult.Success(FeedMutationBatchResultV2(serverId,
                listOf(FeedMutationResultV2(batch.mutations.single().opId, "conflict", snapshot("Web", 5))))) }
        }
        val result = FeedSyncV2UseCase(store, store, remote).sync()
        assertTrue(result is FeedSyncV2Outcome.Partial)
        assertEquals("Web", db.feedDao().getFeedByUrl(url)!!.name)
        val proposal = db.feedMutationDao().forUrl(url).single()
        assertEquals("needs_resolution", proposal.state)
        assertTrue(proposal.fieldsJson.contains("Mine"))
        db.close()
    }

    @Test fun `failed push with successful pull stays partial and keeps sent head`() = runBlocking {
        context.deleteDatabase(name)
        val db = database()
        val store = AndroidFeedV2Store(db, settings)
        bound(store, snapshot("Server", 4))
        store.saveLocal(feed("Mine"))
        val remote = Remote().apply {
            pull = { FeedV2RemoteResult.Success(FeedChangesV2Response(serverId, 4, emptyList())) }
            push = { FeedV2RemoteResult.TransportFailure("synthetic timeout") }
        }
        val result = FeedSyncV2UseCase(store, store, remote).sync()
        assertTrue(result is FeedSyncV2Outcome.Partial)
        assertEquals("push", (result as FeedSyncV2Outcome.Partial).phase)
        assertEquals(1, result.pending)
        assertTrue(db.feedMutationDao().forUrl(url).single().sent)
        assertEquals(4L, db.feedSyncStateDao().active()!!.cursorVersion)
        db.close()
    }

    @Test fun `v2 404 and 405 require upgrade and preserve local pending without v1 write`() = runBlocking {
        for (status in listOf(404, 405)) {
            context.deleteDatabase(name)
            val db = database()
            val store = AndroidFeedV2Store(db, settings)
            store.saveLocal(feed("Offline"))
            val remote = Remote().apply {
                pull = { FeedV2RemoteResult.HttpFailure(status, null) }
                push = { error("No v2 mutation should be sent") }
            }
            val result = FeedSyncV2UseCase(store, store, remote).sync()
            assertEquals(FeedSyncV2Outcome.ServerUpgradeRequired, result)
            assertTrue(remote.batches.isEmpty())
            assertEquals("Offline", db.feedDao().getFeedByUrl(url)!!.name)
            assertEquals(1, db.feedMutationDao().forUrl(url).size)
            assertFalse(db.feedSyncStateDao().active()!!.firstBindingComplete)
            store.recordOutcome(result)
            assertEquals("server_upgrade_required", db.feedSyncStateDao().active()!!.lastOutcome)
            db.close()
        }
    }
}
