package com.example.epilog.service

import com.example.epilog.domain.model.ProcessedArticle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import net.dankito.readability4j.Readability4J
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Processes web content using Jsoup for fetching and Readability4J for extraction.
 * Extracts clean article content by removing ads, sidebars, and navigation elements.
 */
@Singleton
class ContentProcessor @Inject constructor() {

    companion object {
        private const val DEFAULT_TIMEOUT_MS = 60_000
        private const val DEFAULT_MIN_WORD_COUNT = 0
        private const val USER_AGENT = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    }

    /**
     * Fetches and processes a URL to extract clean article content.
     *
     * @param url The URL to fetch and process
     * @param minWordCount Minimum word count threshold; articles below this are skipped
     * @return ProcessedArticle if successful, null if fetching/parsing fails or word count is below threshold
     */
    suspend fun process(
        url: String,
        minWordCount: Int = DEFAULT_MIN_WORD_COUNT
    ): ProcessedArticle? = withContext(Dispatchers.IO) {
        try {
            val document = fetchDocument(url)
            processDocument(url, document, minWordCount)
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Processes an already-fetched HTML document.
     * Useful for testing or when document is obtained from cache.
     *
     * @param url The original URL (used for resolving relative links)
     * @param document The Jsoup Document to process
     * @param minWordCount Minimum word count threshold
     * @return ProcessedArticle if successful, null otherwise
     */
    fun processDocument(
        url: String,
        document: Document,
        minWordCount: Int = DEFAULT_MIN_WORD_COUNT
    ): ProcessedArticle? {
        val article = extractArticle(url, document) ?: return null

        // Apply word count filter if specified
        if (minWordCount > 0) {
            val wordCount = countWords(article.content)
            if (wordCount < minWordCount) {
                return null
            }
        }

        return article
    }

    /**
     * Fetches HTML document from URL using Jsoup.
     */
    private fun fetchDocument(url: String): Document {
        return Jsoup.connect(url)
            .userAgent(USER_AGENT)
            .timeout(DEFAULT_TIMEOUT_MS)
            .followRedirects(true)
            .get()
    }

    /**
     * Extracts article content using Readability4J.
     */
    private fun extractArticle(url: String, document: Document): ProcessedArticle? {
        val readability = Readability4J(url, document)
        val article = readability.parse()

        val title = article.title?.trim()
        val content = article.articleContent?.html()

        // Require at least title and content
        if (title.isNullOrBlank() || content.isNullOrBlank()) {
            return null
        }

        // Clean up the extracted HTML
        val cleanedContent = cleanHtml(content)

        return ProcessedArticle(
            title = title,
            author = article.byline?.trim() ?: "",
            content = cleanedContent,
            originalUrl = url,
            isSummary = false
        )
    }

    /**
     * Cleans extracted HTML content.
     * Removes empty elements and normalizes whitespace.
     */
    private fun cleanHtml(html: String): String {
        val doc = Jsoup.parseBodyFragment(html)

        // Remove empty paragraphs and divs
        doc.select("p:empty, div:empty, span:empty").remove()

        // Remove style and class attributes for cleaner output
        doc.select("[style]").removeAttr("style")
        doc.select("[class]").removeAttr("class")

        // Remove script and style tags (shouldn't be present, but safety measure)
        doc.select("script, style, noscript").remove()

        // Remove tracking pixels and hidden images
        doc.select("img[width=1], img[height=1], img[src*='pixel'], img[src*='track']").remove()

        return doc.body().html()
    }

    /**
     * Counts words in HTML content by stripping tags first.
     */
    private fun countWords(html: String): Int {
        val text = Jsoup.parse(html).text()
        return text.split(Regex("\\s+"))
            .filter { it.isNotBlank() }
            .size
    }
}
