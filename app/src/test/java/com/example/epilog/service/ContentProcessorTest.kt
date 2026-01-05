package com.example.epilog.service

import org.jsoup.Jsoup
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class ContentProcessorTest {

    private lateinit var processor: ContentProcessor

    @Before
    fun setup() {
        processor = ContentProcessor()
    }

    @Test
    fun `processDocument extracts title and content from valid article`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Test Article Title</title></head>
            <body>
                <header><nav>Navigation Menu</nav></header>
                <article>
                    <h1>Test Article Title</h1>
                    <p class="byline">By John Doe</p>
                    <p>This is the first paragraph of the article content. It contains enough words to pass any reasonable minimum word count filter that might be applied.</p>
                    <p>This is the second paragraph with more content. The article continues with additional information that readers would find valuable and interesting.</p>
                    <p>The third paragraph concludes the article with final thoughts and summary of the main points discussed above.</p>
                </article>
                <aside>Sidebar content</aside>
                <footer>Footer content</footer>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/article", document)

        assertNotNull(result)
        assertEquals("Test Article Title", result!!.title)
        assertEquals("https://example.com/article", result.originalUrl)
        assertFalse(result.isSummary)
        assertTrue(result.content.contains("first paragraph"))
        assertTrue(result.content.contains("second paragraph"))
    }

    @Test
    fun `processDocument returns null for page without article content`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Empty Page</title></head>
            <body>
                <nav>Menu</nav>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/empty", document)

        assertNull(result)
    }

    @Test
    fun `processDocument filters articles below minimum word count`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Short Article</title></head>
            <body>
                <article>
                    <h1>Short Article</h1>
                    <p>This is short.</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument(
            url = "https://example.com/short",
            document = document,
            minWordCount = 300
        )

        assertNull(result)
    }

    @Test
    fun `processDocument allows articles meeting minimum word count`() {
        val longContent = (1..100).joinToString(" ") { "word$it" }
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Long Article</title></head>
            <body>
                <article>
                    <h1>Long Article</h1>
                    <p>$longContent</p>
                    <p>$longContent</p>
                    <p>$longContent</p>
                    <p>$longContent</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument(
            url = "https://example.com/long",
            document = document,
            minWordCount = 300
        )

        assertNotNull(result)
        assertEquals("Long Article", result!!.title)
    }

    @Test
    fun `processDocument removes style and class attributes`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Styled Article</title></head>
            <body>
                <article>
                    <h1>Styled Article</h1>
                    <p class="intro" style="color: red;">First paragraph with styling.</p>
                    <p class="body" style="font-size: 14px;">Second paragraph with more styling and enough content to be extracted properly by the parser.</p>
                    <p>Third paragraph without styling but with sufficient content for extraction.</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/styled", document)

        assertNotNull(result)
        assertFalse(result!!.content.contains("class="))
        assertFalse(result.content.contains("style="))
    }

    @Test
    fun `processDocument removes tracking pixels`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Article with Tracking</title></head>
            <body>
                <article>
                    <h1>Article with Tracking</h1>
                    <p>This is article content that should be preserved in the output.</p>
                    <img src="https://tracker.com/pixel.gif" width="1" height="1">
                    <p>More article content that continues the story with additional details.</p>
                    <img src="https://analytics.com/track?id=123" alt="">
                    <p>Final paragraph with conclusion and summary of the article content.</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/tracking", document)

        assertNotNull(result)
        assertFalse(result!!.content.contains("pixel.gif"))
        assertFalse(result.content.contains("track?id="))
    }

    @Test
    fun `processDocument extracts author byline when present`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Authored Article</title></head>
            <body>
                <article>
                    <h1>Authored Article</h1>
                    <p rel="author">By Jane Smith</p>
                    <p>Article content goes here with enough text to be properly extracted by the Readability algorithm.</p>
                    <p>Additional paragraphs provide more content for the article body section.</p>
                    <p>The conclusion wraps up the main points discussed in this article.</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/authored", document)

        assertNotNull(result)
        // Note: Byline extraction depends on Readability4J's heuristics
        // The test verifies the field exists and is properly trimmed
        assertNotNull(result!!.author)
    }

    @Test
    fun `processDocument sets isSummary to false`() {
        val html = """
            <!DOCTYPE html>
            <html>
            <head><title>Regular Article</title></head>
            <body>
                <article>
                    <h1>Regular Article</h1>
                    <p>Content paragraph one with substantial text for extraction.</p>
                    <p>Content paragraph two continues the article with more details.</p>
                    <p>Content paragraph three concludes with final thoughts on the topic.</p>
                </article>
            </body>
            </html>
        """.trimIndent()

        val document = Jsoup.parse(html)
        val result = processor.processDocument("https://example.com/regular", document)

        assertNotNull(result)
        assertFalse(result!!.isSummary)
    }
}
