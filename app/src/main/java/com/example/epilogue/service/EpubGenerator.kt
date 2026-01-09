package com.example.epilogue.service

import android.content.Context
import android.media.MediaScannerConnection
import android.os.Environment
import com.example.epilogue.domain.model.ProcessedArticle
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import io.documentnode.epub4j.domain.Author
import io.documentnode.epub4j.domain.Book
import io.documentnode.epub4j.domain.Resource
import io.documentnode.epub4j.epub.EpubWriter
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Entities
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * Result of EPUB generation containing the file and articles.
 */
data class EpubGenerationResult(
    val file: File,
    val articles: List<ProcessedArticle>
)

/**
 * Generates EPUB files from processed articles.
 * Separates content into Briefings (summaries) and Deep Dives (full articles).
 */
@Singleton
class EpubGenerator @Inject constructor(
    @ApplicationContext private val context: Context
) {

    companion object {
        private const val EPUB_DIR = "Epilogue"
        private const val MEDIA_TYPE_HTML = "application/xhtml+xml"
        private const val MEDIA_TYPE_CSS = "text/css"
    }

    private val dateFormat = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    private val displayDateFormat = SimpleDateFormat("MMMM d, yyyy", Locale.US)

    /**
     * Generates an EPUB file from a list of processed articles.
     *
     * @param articles List of articles to include
     * @param date Date for the digest (defaults to today)
     * @return Result containing the generated EPUB file and articles, or null if generation fails
     */
    suspend fun generate(
        articles: List<ProcessedArticle>,
        date: Date = Date()
    ): EpubGenerationResult? = withContext(Dispatchers.IO) {
        if (articles.isEmpty()) return@withContext null

        try {
            val book = createBook(articles, date)
            val outputFile = writeEpub(book, date)
            scanFile(outputFile)
            EpubGenerationResult(outputFile, articles)
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Creates an EPUB book from articles.
     */
    private fun createBook(articles: List<ProcessedArticle>, date: Date): Book {
        val book = Book()
        val formattedDate = displayDateFormat.format(date)

        // Metadata
        book.metadata.addTitle("Epilogue - $formattedDate")
        book.metadata.addAuthor(Author("Epilogue"))
        book.metadata.addDescription("Daily digest for $formattedDate")

        // Add stylesheet
        val css = createStylesheet()
        book.resources.add(Resource(css.toByteArray(), "style.css"))

        // Add cover page
        val coverHtml = createCoverPage(formattedDate)
        val coverResource = Resource(coverHtml.toByteArray(), "cover.xhtml")
        book.coverPage = coverResource
        book.addSection("Cover", coverResource)

        // Separate articles by type
        val briefings = articles.filter { it.isSummary }
        val deepDives = articles.filter { !it.isSummary }

        // Section 1: The Briefing (summaries)
        if (briefings.isNotEmpty()) {
            addBriefingsSection(book, briefings)
        }

        // Section 2: Deep Dives (full articles)
        if (deepDives.isNotEmpty()) {
            addDeepDivesSection(book, deepDives)
        }

        return book
    }

    /**
     * Adds the Briefings section containing all AI summaries.
     */
    private fun addBriefingsSection(book: Book, briefings: List<ProcessedArticle>) {
        val briefingHtml = buildString {
            append(createHtmlHeader("The Briefing"))
            append("<body>\n")
            append("<h1>The Briefing</h1>\n")
            append("<p class=\"section-intro\">AI-generated summaries for quick catch-up</p>\n")

            briefings.forEachIndexed { index, article ->
                append("<article>\n")
                append("<h2>${escapeHtml(article.title)}</h2>\n")
                if (article.author.isNotBlank()) {
                    append("<p class=\"byline\">${escapeHtml(article.author)}</p>\n")
                }
                append("<div class=\"content\">${sanitizeHtmlToXhtml(article.content)}</div>\n")
                append("<p class=\"source\"><a href=\"${escapeHtml(article.originalUrl)}\">Source</a></p>\n")
                if (index < briefings.lastIndex) {
                    append("<hr/>\n")
                }
                append("</article>\n")
            }

            append("</body>\n</html>")
        }

        val resource = Resource(briefingHtml.toByteArray(), "briefings.xhtml")
        book.addSection("The Briefing", resource)
    }

    /**
     * Adds the Deep Dives section with each full article as a separate chapter.
     */
    private fun addDeepDivesSection(book: Book, deepDives: List<ProcessedArticle>) {
        // Create section header
        val sectionHeaderHtml = buildString {
            append(createHtmlHeader("Deep Dives"))
            append("<body>\n")
            append("<h1>Deep Dives</h1>\n")
            append("<p class=\"section-intro\">Full articles for in-depth reading</p>\n")
            append("<ul>\n")
            deepDives.forEach { article ->
                append("<li>${escapeHtml(article.title)}</li>\n")
            }
            append("</ul>\n")
            append("</body>\n</html>")
        }

        val sectionResource = Resource(sectionHeaderHtml.toByteArray(), "deep-dives.xhtml")
        val sectionToc = book.addSection("Deep Dives", sectionResource)

        // Add each article as a sub-chapter
        deepDives.forEachIndexed { index, article ->
            val articleHtml = buildString {
                append(createHtmlHeader(article.title))
                append("<body>\n")
                append("<article>\n")
                append("<h1>${escapeHtml(article.title)}</h1>\n")
                if (article.author.isNotBlank()) {
                    append("<p class=\"byline\">By ${escapeHtml(article.author)}</p>\n")
                }
                append("<div class=\"content\">${sanitizeHtmlToXhtml(article.content)}</div>\n")
                append("<p class=\"source\"><a href=\"${escapeHtml(article.originalUrl)}\">Original article</a></p>\n")
                append("</article>\n")
                append("</body>\n</html>")
            }

            val articleResource = Resource(
                articleHtml.toByteArray(),
                "article-${index + 1}.xhtml"
            )
            book.addSection(sectionToc, article.title, articleResource)
        }
    }

    /**
     * Creates the cover page HTML.
     */
    private fun createCoverPage(formattedDate: String): String = buildString {
        append(createHtmlHeader("Epilogue"))
        append("<body class=\"cover\">\n")
        append("<div class=\"cover-content\">\n")
        append("<h1>Epilogue</h1>\n")
        append("<p class=\"date\">$formattedDate</p>\n")
        append("<p class=\"tagline\">Your Daily Reading Digest</p>\n")
        append("</div>\n")
        append("</body>\n</html>")
    }

    /**
     * Creates the HTML header with stylesheet link.
     */
    private fun createHtmlHeader(title: String): String = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE html>
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <title>${escapeHtml(title)}</title>
            <link rel="stylesheet" type="text/css" href="style.css"/>
        </head>
    """.trimIndent() + "\n"

    /**
     * Creates the stylesheet optimized for e-ink displays.
     */
    private fun createStylesheet(): String = """
        body {
            font-family: serif;
            line-height: 1.6;
            margin: 1em;
            color: #000000;
            background-color: #ffffff;
        }

        h1 {
            font-size: 1.5em;
            margin-bottom: 0.5em;
            border-bottom: 2px solid #000000;
            padding-bottom: 0.25em;
        }

        h2 {
            font-size: 1.25em;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }

        .cover {
            text-align: center;
            padding-top: 30%;
        }

        .cover h1 {
            font-size: 2.5em;
            border: none;
        }

        .cover .date {
            font-size: 1.25em;
            margin-top: 1em;
        }

        .cover .tagline {
            font-style: italic;
            margin-top: 2em;
        }

        .section-intro {
            font-style: italic;
            margin-bottom: 2em;
        }

        .byline {
            font-style: italic;
            color: #333333;
            margin-bottom: 1em;
        }

        .content {
            margin: 1em 0;
        }

        .content p {
            margin-bottom: 1em;
            text-align: justify;
        }

        .content img {
            max-width: 100%;
            height: auto;
        }

        .source {
            font-size: 0.875em;
            margin-top: 1em;
            padding-top: 0.5em;
            border-top: 1px solid #cccccc;
        }

        hr {
            border: none;
            border-top: 1px solid #cccccc;
            margin: 2em 0;
        }

        a {
            color: #000000;
            text-decoration: underline;
        }

        article {
            margin-bottom: 2em;
        }

        blockquote {
            margin: 1em 2em;
            padding-left: 1em;
            border-left: 3px solid #000000;
            font-style: italic;
        }

        pre, code {
            font-family: monospace;
            font-size: 0.9em;
            background-color: #f5f5f5;
            padding: 0.25em;
        }

        pre {
            padding: 1em;
            overflow-x: auto;
            white-space: pre-wrap;
        }
    """.trimIndent()

    /**
     * Writes the EPUB book to a file.
     */
    private fun writeEpub(book: Book, date: Date): File {
        val outputDir = getOutputDirectory()
        outputDir.mkdirs()

        val filename = "Epilogue_${dateFormat.format(date)}.epub"
        val outputFile = File(outputDir, filename)

        FileOutputStream(outputFile).use { fos ->
            EpubWriter().write(book, fos)
        }

        return outputFile
    }

    /**
     * Gets the output directory for EPUB files.
     * Uses /Documents/Epilogue/ on external storage.
     */
    private fun getOutputDirectory(): File {
        val documentsDir = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DOCUMENTS
        )
        return File(documentsDir, EPUB_DIR)
    }

    /**
     * Triggers the MediaScanner to make the file visible in file browsers and the Boox Library.
     * This is critical for the file to appear without a device reboot.
     */
    private suspend fun scanFile(file: File) = suspendCancellableCoroutine { continuation ->
        MediaScannerConnection.scanFile(
            context,
            arrayOf(file.absolutePath),
            arrayOf("application/epub+zip")
        ) { _, _ ->
            if (continuation.isActive) {
                continuation.resume(Unit)
            }
        }
    }

    /**
     * Escapes HTML special characters.
     */
    private fun escapeHtml(text: String): String = text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\"", "&quot;")
        .replace("'", "&#39;")

    /**
     * Sanitizes HTML content to be valid XHTML for EPUB.
     * Converts HTML to XHTML-compliant markup using Jsoup.
     */
    private fun sanitizeHtmlToXhtml(html: String): String {
        if (html.isBlank()) return ""

        val doc = Jsoup.parseBodyFragment(html)

        // Configure output for XHTML
        doc.outputSettings()
            .syntax(Document.OutputSettings.Syntax.xml)
            .escapeMode(Entities.EscapeMode.xhtml)
            .charset("UTF-8")

        // Remove potentially problematic elements
        doc.select("script, style, iframe, object, embed, form, input, button").remove()

        // Fix common issues: convert self-closing tags to XHTML format
        // Jsoup handles this automatically with xml syntax

        // Remove invalid attributes that might cause issues
        doc.select("[onclick], [onload], [onerror]").forEach { it.clearAttributes() }

        return doc.body().html()
    }
}
