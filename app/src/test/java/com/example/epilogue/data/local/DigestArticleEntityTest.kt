package com.example.epilogue.data.local

import com.example.epilogue.domain.model.ProcessedArticle
import org.junit.Assert.assertEquals
import org.junit.Test

class DigestArticleEntityTest {

    @Test
    fun `toDomain maps fields`() {
        val entity = DigestArticleEntity(
            id = 5L,
            digestId = 10L,
            title = "Title",
            author = "Author",
            content = "<p>Content</p>",
            originalUrl = "https://example.com",
            isSummary = true,
            feedName = "Feed",
            sortOrder = 2
        )

        val domain = entity.toDomain()

        assertEquals(entity.id, domain.id)
        assertEquals(entity.title, domain.title)
        assertEquals(entity.author, domain.author)
        assertEquals(entity.content, domain.content)
        assertEquals(entity.originalUrl, domain.originalUrl)
        assertEquals(entity.isSummary, domain.isSummary)
        assertEquals(entity.feedName, domain.feedName)
    }

    @Test
    fun `fromProcessedArticle maps fields`() {
        val article = ProcessedArticle(
            title = "Article",
            author = "Author",
            content = "<p>Body</p>",
            originalUrl = "https://example.com",
            isSummary = false
        )

        val entity = DigestArticleEntity.fromProcessedArticle(
            digestId = 7L,
            article = article,
            feedName = "Feed",
            sortOrder = 1
        )

        assertEquals(7L, entity.digestId)
        assertEquals("Article", entity.title)
        assertEquals("Author", entity.author)
        assertEquals("<p>Body</p>", entity.content)
        assertEquals("https://example.com", entity.originalUrl)
        assertEquals(false, entity.isSummary)
        assertEquals("Feed", entity.feedName)
        assertEquals(1, entity.sortOrder)
    }
}
