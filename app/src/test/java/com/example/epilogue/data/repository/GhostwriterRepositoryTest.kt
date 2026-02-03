package com.example.epilogue.data.repository

import android.content.Context
import com.example.epilogue.data.remote.ghostwriter.FeedSyncResponse
import com.example.epilogue.data.remote.ghostwriter.GhostwriterApi
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.di.GhostwriterApiFactory
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

class GhostwriterRepositoryTest {

    private val context: Context = mockk(relaxed = true)
    private val settingsRepository: SettingsRepository = mockk()
    private val apiFactory: GhostwriterApiFactory = mockk()
    private val api: GhostwriterApi = mockk()

    private val repository = GhostwriterRepository(
        context = context,
        settingsRepository = settingsRepository,
        apiFactory = apiFactory
    )

    @Test
    fun `checkHealth returns NotConfigured when ghostwriter disabled`() = runTest {
        every { settingsRepository.getGhostwriterUrl() } returns null
        every { settingsRepository.isGhostwriterEnabled() } returns false

        val result = repository.checkHealth()

        assertTrue(result is GhostwriterRepository.GhostwriterResult.NotConfigured)
        verify(exactly = 0) { apiFactory.create(any()) }
    }

    @Test
    fun `syncFeeds maps mode and max articles`() = runTest {
        every { settingsRepository.getGhostwriterUrl() } returns "https://ghostwriter.test"
        every { settingsRepository.isGhostwriterEnabled() } returns true
        every { settingsRepository.getGhostwriterApiKey() } returns "key"
        every { apiFactory.create(any()) } returns api

        val requestSlot = slot<List<com.example.epilogue.data.remote.ghostwriter.FeedSyncRequest>>()
        coEvery { api.syncFeeds(any(), capture(requestSlot)) } returns
            Response.success(FeedSyncResponse(2, 0, 0, 2))

        val feeds = listOf(
            Feed("https://example.com/rss", "Example", ProcessingMode.BRIEFING, maxArticles = 0),
            Feed("https://example.com/raw", "Raw", ProcessingMode.FIDELITY, maxArticles = 5)
        )

        val result = repository.syncFeeds(feeds)

        assertTrue(result is GhostwriterRepository.GhostwriterResult.Success)
        val requests = requestSlot.captured
        assertEquals(2, requests.size)
        assertEquals("summarize", requests[0].mode)
        assertEquals(10, requests[0].maxArticles)
        assertEquals("raw", requests[1].mode)
        assertEquals(5, requests[1].maxArticles)
    }

    @Test
    fun `triggerDigest returns conflict error on 409`() = runTest {
        every { settingsRepository.getGhostwriterUrl() } returns "https://ghostwriter.test"
        every { settingsRepository.isGhostwriterEnabled() } returns true
        every { settingsRepository.getGhostwriterApiKey() } returns "key"
        every { apiFactory.create(any()) } returns api

        coEvery { api.triggerDigest(any(), any()) } returns
            Response.error(409, "conflict".toResponseBody())

        val result = repository.triggerDigest()

        assertTrue(result is GhostwriterRepository.GhostwriterResult.Error)
        assertEquals(409, (result as GhostwriterRepository.GhostwriterResult.Error).code)
    }

    @Test
    fun `deleteFeedByUrl returns success on 404`() = runTest {
        every { settingsRepository.getGhostwriterUrl() } returns "https://ghostwriter.test"
        every { settingsRepository.isGhostwriterEnabled() } returns true
        every { settingsRepository.getGhostwriterApiKey() } returns "key"
        every { apiFactory.create(any()) } returns api

        coEvery { api.deleteFeedByUrl(any(), any()) } returns
            Response.error(404, "not found".toResponseBody())

        val result = repository.deleteFeedByUrl("https://example.com/rss")

        assertTrue(result is GhostwriterRepository.GhostwriterResult.Success)
    }
}
