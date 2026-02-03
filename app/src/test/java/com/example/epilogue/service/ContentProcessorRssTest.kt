package com.example.epilogue.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ContentProcessorRssTest {

    private lateinit var processor: ContentProcessor

    @Before
    fun setup() {
        processor = ContentProcessor(ContentAnalyzer())
    }

    @Test
    fun `processWithRssContent uses rss content for full article`() = kotlinx.coroutines.runBlocking {
        val paragraph = words(80)
        val html = """
            <article>
                <h1>RSS Title</h1>
                <p class="intro" style="color: red;">$paragraph</p>
                <p>$paragraph</p>
                <p>$paragraph</p>
                <img src="https://tracker.com/pixel.gif" width="1" height="1" />
            </article>
        """.trimIndent()

        val result = processor.processWithRssContent(
            url = "https://example.com/article",
            rssContent = html,
            rssDescription = null,
            rssTitle = "RSS Title",
            rssAuthor = "Jane Doe",
            minWordCount = 0
        )

        assertNotNull(result)
        assertEquals("RSS Title", result!!.title)
        assertEquals("Jane Doe", result.author)
        assertFalse(result.isSummary)
        assertTrue(result.content.contains("word"))
        assertFalse(result.content.contains("class="))
        assertFalse(result.content.contains("style="))
        assertFalse(result.content.contains("pixel.gif"))
    }

    @Test
    fun `processWithRssContent accepts uncertain rss content above threshold`() = kotlinx.coroutines.runBlocking {
        val paragraph = words(55) // ~55 words
        val html = """
            <article>
                <p>$paragraph</p>
                <p>$paragraph</p>
                <p>$paragraph</p>
            </article>
        """.trimIndent()

        val result = processor.processWithRssContent(
            url = "https://example.com/uncertain",
            rssContent = html,
            rssDescription = null,
            rssTitle = "Uncertain Article",
            rssAuthor = null,
            minWordCount = 0
        )

        assertNotNull(result)
        assertEquals("Uncertain Article", result!!.title)
        assertTrue(result.content.contains("word"))
    }

    private fun words(count: Int): String {
        return (1..count).joinToString(" ") { "word$it" }
    }
}
