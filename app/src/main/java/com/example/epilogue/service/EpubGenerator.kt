package com.example.epilogue.service

import android.content.Context
import android.media.MediaScannerConnection
import android.os.Environment
import com.example.epilogue.domain.model.DigestPeriod
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
 * Organizes content into feed chapters with article sub-chapters.
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
     * @param period Optional period (MORNING, NOON, EVENING) for scheduled digests
     * @return Result containing the generated EPUB file and articles, or null if generation fails
     */
    suspend fun generate(
        articles: List<ProcessedArticle>,
        date: Date = Date(),
        period: DigestPeriod? = null
    ): EpubGenerationResult? = withContext(Dispatchers.IO) {
        if (articles.isEmpty()) return@withContext null

        try {
            val book = createBook(articles, date, period)
            val outputFile = writeEpub(book, date, period)
            scanFile(outputFile)
            EpubGenerationResult(outputFile, articles)
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Creates an EPUB book from articles.
     */
    private fun createBook(articles: List<ProcessedArticle>, date: Date, period: DigestPeriod?): Book {
        val book = Book()
        val formattedDate = displayDateFormat.format(date)
        val periodText = period?.name?.lowercase()?.replaceFirstChar { it.uppercase() }
        val titleSuffix = periodText?.let { " - $it" } ?: ""
        val descriptionSuffix = periodText?.let { " ($it digest)" } ?: ""

        // Metadata
        book.metadata.addTitle("Epilogue - $formattedDate$titleSuffix")
        book.metadata.addAuthor(Author("Epilogue"))
        book.metadata.addDescription("Daily digest for $formattedDate$descriptionSuffix")

        // Add stylesheet
        val css = createStylesheet()
        book.resources.add(Resource(css.toByteArray(), "style.css"))

        // Add cover page
        val coverHtml = createCoverPage(formattedDate, period)
        val coverResource = Resource(coverHtml.toByteArray(), "cover.xhtml")
        book.coverPage = coverResource
        book.addSection("Cover", coverResource)

        // Feed chapters with article sub-chapters
        val groupedByFeed = groupArticlesByFeed(articles)
        groupedByFeed.forEachIndexed { feedIndex, (feedName, feedArticles) ->
            addFeedSection(
                book = book,
                feedName = feedName,
                articles = feedArticles,
                feedIndex = feedIndex
            )
        }

        return book
    }

    /**
     * Groups articles by feed while preserving first-seen feed order.
     */
    private fun groupArticlesByFeed(
        articles: List<ProcessedArticle>
    ): List<Pair<String, List<ProcessedArticle>>> {
        val grouped = linkedMapOf<String, MutableList<ProcessedArticle>>()
        articles.forEach { article ->
            val feedName = article.feedName.ifBlank { "Unknown Feed" }
            grouped.getOrPut(feedName) { mutableListOf() }.add(article)
        }
        return grouped.map { (feedName, feedArticles) ->
            feedName to feedArticles.toList()
        }
    }

    /**
     * Adds a feed chapter and each feed article as a sub-chapter.
     */
    private fun addFeedSection(
        book: Book,
        feedName: String,
        articles: List<ProcessedArticle>,
        feedIndex: Int
    ) {
        val sectionHeaderHtml = buildString {
            append(createHtmlHeader(feedName))
            append("<body>\n")
            append("<h1>${escapeHtml(feedName)}</h1>\n")
            append("<p class=\"section-intro\">${articles.size} article${if (articles.size == 1) "" else "s"}</p>\n")
            append("</body>\n</html>")
        }

        val feedSlug = slugify(feedName)
        val sectionResource = Resource(
            sectionHeaderHtml.toByteArray(),
            "feed-${feedIndex + 1}-$feedSlug.xhtml"
        )
        val sectionToc = book.addSection(feedName, sectionResource)

        articles.forEachIndexed { index, article ->
            val articleHtml = buildString {
                append(createHtmlHeader(article.title))
                append("<body>\n")
                append("<article>\n")
                append("<h1>${escapeHtml(article.title)}</h1>\n")
                if (article.author.isNotBlank()) {
                    append("<p class=\"byline\">By ${escapeHtml(article.author)}</p>\n")
                }
                if (article.isSummary) {
                    append("<p class=\"section-intro\">Briefing</p>\n")
                }
                append("<div class=\"content\">${sanitizeHtmlToXhtml(article.content)}</div>\n")
                append("<p class=\"source\"><a href=\"${escapeHtml(article.originalUrl)}\">Original article</a></p>\n")
                append("</article>\n")
                append("</body>\n</html>")
            }

            val articleResource = Resource(
                articleHtml.toByteArray(),
                "feed-${feedIndex + 1}-article-${index + 1}-$feedSlug.xhtml"
            )
            book.addSection(sectionToc, article.title, articleResource)
        }
    }

    private fun slugify(value: String): String {
        val normalized = value.lowercase(Locale.ROOT)
            .replace(Regex("[^a-z0-9]+"), "-")
            .trim('-')
        return if (normalized.isBlank()) "feed" else normalized
    }

    /**
     * Creates the cover page HTML.
     */
    private fun createCoverPage(formattedDate: String, period: DigestPeriod?): String = buildString {
        append(createHtmlHeader("Epilogue"))
        append("<body class=\"cover\">\n")
        append("<div class=\"cover-content\">\n")
        append("<h1>Epilogue</h1>\n")
        append("<p class=\"date\">$formattedDate</p>\n")
        if (period != null) {
            val periodName = period.name.lowercase().replaceFirstChar { it.uppercase() }
            append("<p class=\"period\">$periodName Digest</p>\n")
        }
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

        .cover .period {
            font-size: 1.1em;
            font-weight: bold;
            margin-top: 0.5em;
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
     * If a period is provided, includes it in the filename (e.g., "Epilogue_2024-01-11_morning.epub").
     */
    private fun writeEpub(book: Book, date: Date, period: DigestPeriod?): File {
        val outputDir = getOutputDirectory()
        outputDir.mkdirs()

        val periodSuffix = period?.let { "_${it.name.lowercase()}" } ?: ""
        val filename = "Epilogue_${dateFormat.format(date)}${periodSuffix}.epub"
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
