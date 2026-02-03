package com.example.epilogue.data.repository

import com.example.epilogue.data.local.FeedDao
import com.example.epilogue.data.local.FeedEntity
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class FeedRepositoryTest {

    private val feedDao: FeedDao = mockk(relaxed = true)
    private val repository = FeedRepository(feedDao)

    @Test
    fun `getAllFeeds maps entities to domain`() = runTest {
        val entity = FeedEntity(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.BRIEFING,
            lastFetched = 12L,
            maxArticles = 3,
            serverUpdatedAt = 55L,
            locallyModified = true
        )
        every { feedDao.getAllFeeds() } returns flowOf(listOf(entity))

        val result = repository.getAllFeeds().first()

        assertEquals(1, result.size)
        assertEquals(entity.url, result[0].url)
        assertEquals(entity.name, result[0].name)
        assertEquals(entity.mode, result[0].mode)
        assertEquals(entity.lastFetched, result[0].lastFetched)
        assertEquals(entity.maxArticles, result[0].maxArticles)
        assertEquals(entity.serverUpdatedAt, result[0].serverUpdatedAt)
        assertEquals(entity.locallyModified, result[0].locallyModified)
    }

    @Test
    fun `deleteByUrls skips DAO call for empty list`() = runTest {
        repository.deleteByUrls(emptyList())

        coVerify(exactly = 0) { feedDao.deleteByUrls(any()) }
    }

    @Test
    fun `upsertAll skips DAO call for empty list`() = runTest {
        repository.upsertAll(emptyList())

        coVerify(exactly = 0) { feedDao.upsertAll(any()) }
    }

    @Test
    fun `insertFeedWithSync marks feed as locally modified`() = runTest {
        val feed = Feed(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.FIDELITY,
            lastFetched = 0L,
            maxArticles = 0,
            serverUpdatedAt = null,
            locallyModified = false
        )

        val slot = slot<FeedEntity>()
        coEvery { feedDao.insertFeed(capture(slot)) } returns Unit

        repository.insertFeedWithSync(feed)

        assertEquals(true, slot.captured.locallyModified)
        assertEquals(feed.url, slot.captured.url)
    }
}
