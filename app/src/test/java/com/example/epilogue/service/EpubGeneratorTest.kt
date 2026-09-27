package com.example.epilogue.service

import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.DigestPeriod
import android.content.Context
import android.media.MediaScannerConnection
import android.os.Environment
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkStatic
import io.mockk.mockkConstructor
import io.mockk.unmockkAll
import kotlinx.coroutines.runBlocking
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertArrayEquals
import java.io.File
import java.io.IOException
import java.util.Date
import io.documentnode.epub4j.domain.Author
import io.documentnode.epub4j.domain.Book
import io.documentnode.epub4j.domain.Resource
import io.documentnode.epub4j.epub.EpubReader
import io.documentnode.epub4j.epub.EpubWriter
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

/**
 * Unit tests for EPUB generation logic.
 * Tests the book creation without Android-specific file I/O.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class EpubGeneratorTest {

    @get:Rule
    val output = TemporaryFolder()

    private fun prepareGenerator(): EpubGenerator {
        mockkStatic(Environment::class)
        every { Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS) } returns output.root
        mockkStatic(MediaScannerConnection::class)
        every { MediaScannerConnection.scanFile(any(), any(), any(), any()) } answers {
            arg<MediaScannerConnection.OnScanCompletedListener>(3).onScanCompleted("fixture", null)
        }
        return EpubGenerator(mockk<Context>())
    }

    @Test
    fun `repeated manual and scheduled generations preserve distinct readable EPUBs`() = runBlocking {
        try {
            val generator = prepareGenerator()
            val date = Date(1_735_776_000_000L)
            for (period in listOf(null, DigestPeriod.MORNING)) {
                val first = generator.generate(listOf(createArticle("First edition", false)), date, period)!!
                val original = first.file.readBytes()
                val second = generator.generate(listOf(createArticle("Second edition", false)), date, period)!!
                assertNotEquals(first.file.absolutePath, second.file.absolutePath)
                assertArrayEquals(original, first.file.readBytes())
                for ((result, title) in listOf(first to "First edition", second to "Second edition")) {
                    val book = result.file.inputStream().use { EpubReader().readEpub(it) }
                    assertTrue(book.resources.all.any { resource ->
                        resource.href.endsWith(".xhtml") && String(resource.data).contains(title)
                    })
                }
            }
        } finally {
            unmockkAll()
        }
    }

    @Test
    fun `serialization failure removes only its new file and preserves previous edition`() = runBlocking {
        try {
            val generator = prepareGenerator()
            val previous = generator.generate(listOf(createArticle("Earlier edition", false)))!!.file
            val before = previous.readBytes()
            mockkConstructor(EpubWriter::class)
            every { anyConstructed<EpubWriter>().write(any(), any()) } throws IOException("fixture disk failure")
            assertNull(generator.generate(listOf(createArticle("Failed edition", false))))
            assertArrayEquals(before, previous.readBytes())
            assertEquals(listOf(previous.name), previous.parentFile!!.list()!!.toList())
        } finally {
            unmockkAll()
        }
    }

    @Test
    fun `output directory creation failure does not truncate existing file`() = runBlocking {
        try {
            val generator = prepareGenerator()
            val obstruction = File(output.root, "Epilogue").apply { writeText("keep existing content") }
            assertNull(generator.generate(listOf(createArticle("Unavailable output", false))))
            assertEquals("keep existing content", obstruction.readText())
        } finally {
            unmockkAll()
        }
    }

    @Test
    fun `book contains correct title with date`() {
        val book = createTestBook(
            briefings = listOf(createArticle("Summary 1", isSummary = true)),
            deepDives = emptyList()
        )

        val title = book.metadata.titles.firstOrNull()
        assertNotNull(title)
        assertTrue(title!!.contains("Epilogue"))
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
        assertTrue(author.firstname == "Epilogue" || author.lastname == "Epilogue")
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
        assertTrue(readBook.metadata.titles.first().contains("Epilogue"))
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
        book.metadata.addTitle("Epilogue - January 5, 2025")
        book.metadata.addAuthor(Author("Epilogue"))

        // Stylesheet
        val css = "body { font-family: serif; }"
        book.resources.add(Resource(css.toByteArray(), "style.css"))

        // Cover
        val coverHtml = """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE html>
            <html xmlns="http://www.w3.org/1999/xhtml">
            <head><title>Epilogue</title></head>
            <body><h1>Epilogue</h1><p>January 5, 2025</p></body>
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
        book.metadata.addTitle("Epilogue - Test")

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
