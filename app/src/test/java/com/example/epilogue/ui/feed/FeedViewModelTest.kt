package com.example.epilogue.ui.feed

import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.FeedCorrectionEdits
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.data.local.EpilogueDatabase
import androidx.room.Room
import androidx.lifecycle.viewModelScope
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.sync.FeedV2StoreResult
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.coVerifyOrder
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.Job
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class FeedViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val feeds = mockk<FeedRepository>(relaxed = true)
    private val ghostwriter = mockk<GhostwriterRepository>(relaxed = true)
    private val store = mockk<AndroidFeedV2Store>(relaxed = true)
    private val sync = mockk<FeedSyncV2UseCase>(relaxed = true)

    @Before fun setUp() {
        Dispatchers.setMain(dispatcher)
        every { feeds.getAllFeeds() } returns flowOf(emptyList())
        every { store.unresolved() } returns flowOf(emptyList())
        every { store.status() } returns flowOf(null)
    }

    @After fun tearDown() { Dispatchers.resetMain() }

    private fun model() = FeedViewModel(feeds, ghostwriter, store, sync)

    @Test fun `scheme-less URL keeps add dialog and proposal open`() = runTest(dispatcher) {
        val model = model()
        model.showAddDialog()
        model.addFeed("example.org/rss", "News", ProcessingMode.FIDELITY)
        advanceUntilIdle()
        assertTrue(model.uiState.value.showAddDialog)
        assertNotNull(model.uiState.value.error)
        coVerify(exactly = 0) { feeds.insertFeed(any()) }
    }

    @Test fun `valid URL closes only after successful save`() = runTest(dispatcher) {
        val model = model()
        model.showAddDialog()
        model.addFeed(" https://example.org/rss ", " News ", ProcessingMode.FIDELITY)
        assertTrue(model.uiState.value.showAddDialog)
        advanceUntilIdle()
        coVerify(exactly = 1) { feeds.insertFeed(match<Feed> {
            it.url == "https://example.org/rss" && it.name == "News"
        }) }
        assertFalse(model.uiState.value.showAddDialog)
        assertEquals(null, model.uiState.value.error)
    }

    @Test fun `save failure leaves add dialog open with error`() = runTest(dispatcher) {
        coEvery { feeds.insertFeed(any()) } throws IllegalArgumentException("invalid feed")
        val model = model()
        model.showAddDialog()
        model.addFeed("https://example.org/rss", "News", ProcessingMode.FIDELITY)
        advanceUntilIdle()
        assertTrue(model.uiState.value.showAddDialog)
        assertEquals("invalid feed", model.uiState.value.error)
    }

    @Test fun `correction preserves sparse edit intent across mandatory pre-submit pull`() = runTest(dispatcher) {
        var pulls = 0
        coEvery { store.syncAndRecord(sync) } answers {
            pulls++
            FeedSyncV2Outcome.Complete(0, if (pulls == 1) 1 else 0)
        }
        coEvery { store.correctRejected("head", any<FeedCorrectionEdits>()) } answers {
            assertEquals(1, pulls)
            val edits = secondArg<FeedCorrectionEdits>()
            assertEquals("Corrected", edits.title)
            assertEquals(null, edits.mode)
            assertEquals(null, edits.enabled)
            assertEquals(null, edits.maxArticles)
            true
        }
        model().correctRejected("head", FeedCorrectionEdits(title = "Corrected"))
        advanceUntilIdle()
        coVerifyOrder {
            store.syncAndRecord(sync)
            store.correctRejected("head", any<FeedCorrectionEdits>())
            store.syncAndRecord(sync)
        }
    }

    @Test fun `pre-submit pull changes untouched fields before correction is saved`() = runTest(dispatcher) {
        val context = RuntimeEnvironment.getApplication()
        val database = Room.inMemoryDatabaseBuilder(context, EpilogueDatabase::class.java)
            .allowMainThreadQueries().build()
        try {
            val settings = mockk<SettingsRepository>()
            every { settings.isGhostwriterConfigured() } returns true
            every { settings.getGhostwriterUrl() } returns "https://server.test"
            val realStore = AndroidFeedV2Store(database, settings)
            val destination = realStore.currentDestination()!!
            val token = (realStore.beginSyncRun(destination) as FeedV2StoreResult.Success).value
            val serverId = "11111111-1111-4111-8111-111111111111"
            val feedId = "22222222-2222-4222-8222-222222222222"
            val url = "https://example.test/feed"
            fun remote(version: Long, mode: String, enabled: Boolean, cap: Int) =
                FeedSnapshotV2("feed", feedId, url, version, "Server", enabled, mode, cap)
            val binding = (realStore.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response(serverId, 5, listOf(remote(5, "raw", true, 0))))
                as FeedV2StoreResult.Success).value
            realStore.saveLocal(Feed(url, "Rejected", ProcessingMode.FIDELITY, maxArticles = 0))
            val sent = (realStore.loadPendingMutations(token, binding, 100)
                as FeedV2StoreResult.Success).value.single()
            realStore.recordRejection(token, binding, sent.opId, sent.sentRevision,
                "invalid_fields", "Title invalid")
            var calls = 0
            coEvery { sync.sync() } coAnswers {
                if (++calls == 1) realStore.applyServerChangesAndCursor(token, binding,
                    FeedChangesV2Response(serverId, 6, listOf(remote(6, "summarize", false, 7))))
                FeedSyncV2Outcome.Complete(0, if (calls == 1) 1 else 0)
            }
            val model = FeedViewModel(FeedRepository(database.feedDao(), realStore, settings),
                ghostwriter, realStore, sync)
            val preceding = model.viewModelScope.coroutineContext[Job]!!.children.toSet()
            model.correctRejected(sent.opId, FeedCorrectionEdits(title = "Corrected"))
            val correction = model.viewModelScope.coroutineContext[Job]!!.children
                .first { it !in preceding }
            advanceUntilIdle()
            correction.join()
            val corrected = database.feedMutationDao().forUrl(url).single()
            assertEquals(6L, corrected.baseVersion)
            assertTrue(corrected.fieldsJson.contains("\"title\":\"Corrected\""))
            assertTrue(corrected.fieldsJson.contains("\"mode\":\"summarize\""))
            assertTrue(corrected.fieldsJson.contains("\"is_active\":false"))
            assertTrue(corrected.fieldsJson.contains("\"max_articles\":7"))
            realStore.endSyncRun(token)
        } finally {
            database.close()
        }
    }
}
