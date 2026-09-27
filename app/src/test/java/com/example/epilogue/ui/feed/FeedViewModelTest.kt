package com.example.epilogue.ui.feed

import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.flowOf
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

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
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
}
