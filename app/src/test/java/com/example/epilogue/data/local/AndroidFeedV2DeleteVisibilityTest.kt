package com.example.epilogue.data.local

import androidx.room.Room
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.sync.FeedV2StoreResult
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class AndroidFeedV2DeleteVisibilityTest {
    private val url = "https://example.org/feed"
    private val server = "11111111-1111-4111-8111-111111111111"
    private val id = "22222222-2222-4222-8222-222222222222"
    private fun row(version: Long) = FeedSnapshotV2("feed", id, url, version,
        "Remote", true, "raw", 0)
    private val settings = mockk<SettingsRepository> {
        every { isGhostwriterConfigured() } returns true
        every { getGhostwriterUrl() } returns "https://server.test"
    }
    private fun db() = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(),
        EpilogueDatabase::class.java).allowMainThreadQueries().build()
    private fun <T> value(result: FeedV2StoreResult<T>): T =
        (result as FeedV2StoreResult.Success).value

    @Test fun `newer live pull cannot expose trailing local delete`() = runBlocking {
        val db = db()
        try {
            val store = AndroidFeedV2Store(db, settings)
            val destination = store.currentDestination()!!
            val token = (store.beginSyncRun(destination) as FeedV2StoreResult.Success).value
            val binding = (store.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response(server, 1, listOf(row(1)))) as FeedV2StoreResult.Success).value
            store.saveLocal(Feed(url, "Mine", ProcessingMode.FIDELITY, maxArticles = 0))
            store.deleteLocal(url)
            assertTrue(db.feedDao().getFeedByUrl(url)!!.hiddenDelete)
            assertTrue(db.feedDao().getAllFeedsList().isEmpty())
            assertTrue(store.applyServerChangesAndCursor(token, binding,
                FeedChangesV2Response(server, 2, listOf(row(2)))) is FeedV2StoreResult.Success)
            val projected = db.feedDao().getFeedByUrl(url)!!
            val visible = db.feedDao().getAllFeedsList()
            val enabled = db.feedDao().getEnabledFeedsList()
            val localEligible = db.feedDao().getEnabledLocalFeedsList()
            assertTrue("trailing delete: hidden=${projected.hiddenDelete}, " +
                "visible=${visible.map { it.url }}, enabled=${enabled.map { it.url }}, " +
                "localEligible=${localEligible.map { it.url }}",
                projected.hiddenDelete && visible.isEmpty() && enabled.isEmpty() && localEligible.isEmpty())
        } finally {
            db.close()
        }
    }

    @Test fun `full reconciliation keeps trailing delete hidden`() = runBlocking {
        val db = db()
        try {
            val store = AndroidFeedV2Store(db, settings)
            store.saveLocal(Feed(url, "Mine", ProcessingMode.FIDELITY, maxArticles = 0))
            store.deleteLocal(url)
            val destination = store.currentDestination()!!
            val token = value(store.beginSyncRun(destination))
            assertTrue(store.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response(server, 1, listOf(row(1)))) is FeedV2StoreResult.Success)
            assertTrue(db.feedDao().getFeedByUrl(url)!!.hiddenDelete)
            assertTrue(db.feedDao().getAllFeedsList().isEmpty())
            assertEquals(listOf("upsert", "delete"), db.feedMutationDao().forScope(
                destination.configurationId).sortedBy { it.queueOrder }.map { it.kind })
            store.endSyncRun(token)
        } finally { db.close() }
    }

    @Test fun `later explicit readd remains visible after live pull and older delete acknowledgement`() = runBlocking {
        val db = db()
        try {
            val store = AndroidFeedV2Store(db, settings)
            val destination = store.currentDestination()!!
            val token = value(store.beginSyncRun(destination))
            val binding = value(store.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response(server, 1, listOf(row(1)))))
            store.deleteLocal(url)
            store.saveLocal(Feed(url, "Readded", ProcessingMode.FIDELITY, maxArticles = 0))
            val sent = value(store.loadPendingMutations(token, binding, 100)).single()
            assertEquals("delete", sent.payload.kind)
            assertTrue(store.applyServerChangesAndCursor(token, binding,
                FeedChangesV2Response(server, 2, listOf(row(2)))) is FeedV2StoreResult.Success)
            assertFalse(db.feedDao().getFeedByUrl(url)!!.hiddenDelete)
            assertEquals(1, db.feedDao().getEnabledLocalFeedsList().size)
            val tombstone = FeedSnapshotV2("tombstone", id, url, 3, null, null, null, null)
            assertTrue(store.acknowledge(token, binding, sent.opId, sent.sentRevision,
                tombstone) is FeedV2StoreResult.Success)
            assertFalse(db.feedDao().getFeedByUrl(url)!!.hiddenDelete)
            assertEquals(listOf("upsert"), db.feedMutationDao().forUrl(url).map { it.kind })
            store.endSyncRun(token)
        } finally { db.close() }
    }

    @Test fun `old scope delete cannot hide active scope upsert on live pull`() = runBlocking {
        val db = db()
        try {
            val store = AndroidFeedV2Store(db, settings)
            val destination = store.currentDestination()!!
            val token = value(store.beginSyncRun(destination))
            val binding = value(store.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response(server, 1, listOf(row(1)))))
            store.saveLocal(Feed(url, "Active", ProcessingMode.FIDELITY, maxArticles = 0))
            db.feedMutationDao().insert(FeedMutationEntity(UUID.randomUUID().toString(),
                "old-scope", url, "delete", 1, "{}", 99, "needs_resolution",
                createdAt = 1, sequence = 999, queueOrder = 999))
            assertTrue(store.applyServerChangesAndCursor(token, binding,
                FeedChangesV2Response(server, 2, listOf(row(2)))) is FeedV2StoreResult.Success)
            assertFalse(db.feedDao().getFeedByUrl(url)!!.hiddenDelete)
            assertEquals(1, db.feedDao().getAllFeedsList().size)
            assertEquals("delete", db.feedMutationDao().forScope("old-scope").single().kind)
            store.endSyncRun(token)
        } finally { db.close() }
    }
}
