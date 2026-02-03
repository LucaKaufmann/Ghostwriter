package com.example.epilogue.data.local

import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import org.junit.Assert.assertEquals
import org.junit.Test

class FeedEntityTest {

    @Test
    fun `toDomain maps all fields`() {
        val entity = FeedEntity(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.BRIEFING,
            lastFetched = 123L,
            maxArticles = 5,
            serverUpdatedAt = 456L,
            locallyModified = true
        )

        val domain = entity.toDomain()

        assertEquals(entity.url, domain.url)
        assertEquals(entity.name, domain.name)
        assertEquals(entity.mode, domain.mode)
        assertEquals(entity.lastFetched, domain.lastFetched)
        assertEquals(entity.maxArticles, domain.maxArticles)
        assertEquals(entity.serverUpdatedAt, domain.serverUpdatedAt)
        assertEquals(entity.locallyModified, domain.locallyModified)
    }

    @Test
    fun `fromDomain maps all fields`() {
        val feed = Feed(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.FIDELITY,
            lastFetched = 789L,
            maxArticles = 0,
            serverUpdatedAt = 987L,
            locallyModified = false
        )

        val entity = FeedEntity.fromDomain(feed)

        assertEquals(feed.url, entity.url)
        assertEquals(feed.name, entity.name)
        assertEquals(feed.mode, entity.mode)
        assertEquals(feed.lastFetched, entity.lastFetched)
        assertEquals(feed.maxArticles, entity.maxArticles)
        assertEquals(feed.serverUpdatedAt, entity.serverUpdatedAt)
        assertEquals(feed.locallyModified, entity.locallyModified)
    }
}
