package com.example.epilogue.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ContentAnalyzerTest {

    private val analyzer = ContentAnalyzer()

    @Test
    fun `analyze detects preview with read more link`() {
        val html = """
            <p>This is a short preview.</p>
            <a href="https://example.com/full">Read more</a>
        """.trimIndent()

        val result = analyzer.analyze(html, null)

        assertEquals(ContentAnalyzer.ContentType.PREVIEW, result.contentType)
        assertTrue(result.hasReadMoreLink)
        assertFalse(result.extractedText.isBlank())
        assertTrue(result.confidence >= 0.7f)
    }

    @Test
    fun `analyze detects full article with multiple paragraphs`() {
        val paragraph = words(80) + "."
        val html = """
            <article>
                <p>$paragraph</p>
                <p>$paragraph</p>
                <p>$paragraph</p>
            </article>
        """.trimIndent()

        val result = analyzer.analyze(html, null)

        assertEquals(ContentAnalyzer.ContentType.FULL_ARTICLE, result.contentType)
        assertFalse(result.hasReadMoreLink)
        assertFalse(result.isTruncated)
        assertTrue(result.wordCount >= 200)
    }

    @Test
    fun `analyze detects truncation as preview`() {
        val paragraph = words(80) + " ..."
        val html = "<p>$paragraph</p>"

        val result = analyzer.analyze(html, null)

        assertEquals(ContentAnalyzer.ContentType.PREVIEW, result.contentType)
        assertTrue(result.isTruncated)
    }

    @Test
    fun `extractReadMoreUrl returns first matching link`() {
        val html = """
            <p>Short preview</p>
            <a href="https://example.com/full">Read more</a>
        """.trimIndent()

        val url = analyzer.extractReadMoreUrl(html)

        assertNotNull(url)
        assertEquals("https://example.com/full", url)
    }

    private fun words(count: Int): String {
        return (1..count).joinToString(" ") { "word$it" }
    }
}
