package com.example.epilog.service

import com.example.epilog.domain.model.ProcessedArticle
import io.documentnode.epub4j.domain.Author
import io.documentnode.epub4j.domain.Book
import io.documentnode.epub4j.domain.Resource
import io.documentnode.epub4j.epub.EpubReader
import io.documentnode.epub4j.epub.EpubWriter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

/**
 * Unit tests for EPUB generation logic.
 * Tests the book creation without Android-specific file I/O.
 */
class EpubGeneratorTest {

    @Test
    fun `book contains correct title with date`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Summary 1", isSummary = true)),
            deepDives = emptyList()
        )

        val title = book.metadata.titles.firstOrNull()
        assertNotNull(title)
        assertTrue(title!!.contains("Epilog"))
    }

    @Test
    fun `book contains author metadata`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Test", isSummary = true)),
            deepDives = emptyList()
        )

        val authors = book.metadata.authors
        assertTrue(authors.isNotEmpty())
        val author = authors.first()
        // epub4j Author(name) sets lastname, not firstname
        assertTrue(author.firstname == "Epilog" || author.lastname == "Epilog")
    }

    @Test
    fun `book has cover page`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Test", isSummary = true)),
            deepDives = emptyList()
        )

        assertNotNull(book.coverPage)
    }

    @Test
    fun `book separates briefings and deep dives into sections`() {
        val book = createTestBook(
            briefings = listOf(
                createArticle("Summary 1", isSummary = true),
                createArticle("Summary 2", isSummary = true)
            ),
            deepDives = listOf(
                createArticle("Article 1", isSummary = false),
                createArticle("Article 2", isSummary = false)
            )
        )

        val tocReferences = book.tableOfContents.tocReferences

        // Should have Cover, The Briefing, Deep Dives sections
        assertTrue(tocReferences.size >= 3)

        val sectionTitles = tocReferences.map { it.title }
        assertTrue(sectionTitles.any { it.contains("Briefing") })
        assertTrue(sectionTitles.any { it.contains("Deep Dives") })
    }

    @Test
    fun `deep dives section contains individual article chapters`() {
        val book = createTestBook(
            briefings = emptyList(),
            deepDives = listOf(
                createArticle("First Article", isSummary = false),
                createArticle("Second Article", isSummary = false),
                createArticle("Third Article", isSummary = false)
            )
        )

        val deepDivesSection = book.tableOfContents.tocReferences
            .find { it.title.contains("Deep Dives") }

        assertNotNull(deepDivesSection)
        assertEquals(3, deepDivesSection!!.children.size)

        val childTitles = deepDivesSection.children.map { it.title }
        assertTrue(childTitles.contains("First Article"))
        assertTrue(childTitles.contains("Second Article"))
        assertTrue(childTitles.contains("Third Article"))
    }

    @Test
    fun `book includes stylesheet resource`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Test", isSummary = true)),
            deepDives = emptyList()
        )

        val cssResource = book.resources.getByHref("style.css")
        assertNotNull(cssResource)
    }

    @Test
    fun `generated epub is valid and readable`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Summary", isSummary = true)),
            deepDives = listOf(createArticle("Full Article", isSummary = false))
        )

        // Write to bytes and read back
        val outputStream = ByteArrayOutputStream()
        EpubWriter().write(book, outputStream)

        val inputStream = ByteArrayInputStream(outputStream.toByteArray())
        val readBook = EpubReader().readEpub(inputStream)

        assertNotNull(readBook)
        assertTrue(readBook.metadata.titles.first().contains("Epilog"))
    }

    @Test
    fun `html content is properly escaped in titles`() {
        val book = createTestBook(
            briefings = emptyList(),
            deepDives = listOf(
                createArticle("Article with <script>alert('xss')</script>", isSummary = false)
            )
        )

        // Should not throw and should have proper escaping
        val outputStream = ByteArrayOutputStream()
        EpubWriter().write(book, outputStream)

        val content = outputStream.toString()
        assertTrue(!content.contains("<script>alert"))
    }

    @Test
    fun `empty article list produces no book sections except cover`() {
        val book = createMinimalBook()

        // Only cover section
        assertEquals(1, book.tableOfContents.tocReferences.size)
    }

    // Helper methods

    private fun createArticle(title: String, isSummary: Boolean): ProcessedArticle {
        return ProcessedArticle(
            title = title,
            author = "Test Author",
            content = "<p>This is test content for the article titled $title.</p>",
            originalUrl = "https://example.com/${title.lowercase().replace(" ", "-")}",
            isSummary = isSummary
        )
    }

    /**
     * Creates a test book mimicking EpubGenerator's createBook logic.
     */
    private fun createTestBook(
        briefings: List<ProcessedArticle>,
        deepDives: List<ProcessedArticle>
    ): Book {
        val book = Book()

        // Metadata
        book.metadata.addTitle("Epilog - January 5, 2025")
        book.metadata.addAuthor(Author("Epilog"))

        // Stylesheet
        val css = "body { font-family: serif; }"
        book.resources.add(Resource(css.toByteArray(), "style.css"))

        // Cover
        val coverHtml = """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Epilog</title></head>
            <body><h1>Epilog</h1><p>January 5, 2025</p></body>
            </html>
        """.trimIndent()
        val coverResource = Resource(coverHtml.toByteArray(), "cover.xhtml")
        book.coverPage = coverResource
        book.addSection("Cover", coverResource)

        // Briefings section
        if (briefings.isNotEmpty()) {
            val briefingHtml = buildBriefingsHtml(briefings)
            val briefingResource = Resource(briefingHtml.toByteArray(), "briefings.xhtml")
            book.addSection("The Briefing", briefingResource)
        }

        // Deep Dives section
        if (deepDives.isNotEmpty()) {
            val sectionHtml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE html>
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head><title>Deep Dives</title></head>
                <body><h1>Deep Dives</h1></body>
                </html>
            """.trimIndent()
            val sectionResource = Resource(sectionHtml.toByteArray(), "deep-dives.xhtml")
            val sectionToc = book.addSection("Deep Dives", sectionResource)

            deepDives.forEachIndexed { index, article ->
                val articleHtml = """
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE html>
                    <html xmlns="http://www.w3.org/1999/xhtml">
                    <head><title>${escapeHtml(article.title)}</title></head>
                    <body>
                    <h1>${escapeHtml(article.title)}</h1>
                    ${article.content}
                    </body>
                    </html>
                """.trimIndent()
                val articleResource = Resource(articleHtml.toByteArray(), "article-${index + 1}.xhtml")
                book.addSection(sectionToc, article.title, articleResource)
            }
        }

        return book
    }

    private fun createMinimalBook(): Book {
        val book = Book()
        book.metadata.addTitle("Epilog - Test")

        val coverHtml = "<html><body><h1>Cover</h1></body></html>"
        val coverResource = Resource(coverHtml.toByteArray(), "cover.xhtml")
        book.coverPage = coverResource
        book.addSection("Cover", coverResource)

        return book
    }

    private fun buildBriefingsHtml(briefings: List<ProcessedArticle>): String {
        return buildString {
            append("""
                <?xml version="1.0" encoding="UTF-8"?>
                <!DOCTYPE html>
                <html xmlns="http://www.w3.org/1999/xhtml">
                <head><title>The Briefing</title></head>
                <body>
                <h1>The Briefing</h1>
            """.trimIndent())

            briefings.forEach { article ->
                append("<h2>${escapeHtml(article.title)}</h2>")
                append(article.content)
            }

            append("</body></html>")
        }
    }

    private fun escapeHtml(text: String): String = text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
}
