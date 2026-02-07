package com.example.epilogue.service

import android.util.Log
import com.example.epilogue.domain.model.ProcessedArticle
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
 *
 * Supports smart fetching: analyzes RSS content to determine if it's a full article
 * or just a preview, fetching from the URL only when necessary.
 */
@Singleton
class ContentProcessor @Inject constructor(
    private val contentAnalyzer: ContentAnalyzer
) {

    companion object {
        private const val TAG = "ContentProcessor"
        private const val DEFAULT_TIMEOUT_MS = 60_000
        private const val DEFAULT_MIN_WORD_COUNT = 0
        private const val MIN_EXTRACTED_WORDS = 20
        private const val USER_AGENT = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

        // Minimum word count to use RSS content directly
        private const val MIN_RSS_CONTENT_WORDS = 150
    }

    /**
     * Smart content processing that analyzes RSS content before deciding to fetch.
     *
     * Strategy:
     * 1. Analyze RSS content to detect if it's a full article or preview
     * 2. If full article: use RSS content directly (saves HTTP request)
     * 3. If preview: fetch full article from URL
     * 4. If uncertain: try RSS content, fetch if inadequate
     *
     * @param url The article URL
     * @param rssContent The content from RSS item (content:encoded field)
     * @param rssDescription The description/summary from RSS item
     * @param rssTitle The title from RSS item
     * @param rssAuthor The author from RSS item
     * @param minWordCount Minimum word count threshold
     * @return ProcessedArticle if successful, null otherwise
     */
    suspend fun processWithRssContent(
        url: String,
        rssContent: String?,
        rssDescription: String?,
        rssTitle: String?,
        rssAuthor: String?,
        minWordCount: Int = DEFAULT_MIN_WORD_COUNT
    ): ProcessedArticle? = withContext(Dispatchers.IO) {
        try {
            val analysis = contentAnalyzer.analyze(rssContent, rssDescription)

            Log.d(TAG, "Content analysis for $url: type=${analysis.contentType}, " +
                    "words=${analysis.wordCount}, readMore=${analysis.hasReadMoreLink}, " +
                    "truncated=${analysis.isTruncated}, confidence=${analysis.confidence}")

            when (analysis.contentType) {
                ContentAnalyzer.ContentType.FULL_ARTICLE -> {
                    // RSS has full content - process directly
                    processRssContent(
                        url = url,
                        htmlContent = rssContent ?: rssDescription ?: "",
                        rssTitle = rssTitle,
                        rssAuthor = rssAuthor,
                        minWordCount = minWordCount
                    ) ?: run {
                        // Fallback to URL fetch if RSS processing fails
                        Log.d(TAG, "RSS content processing failed, fetching from URL: $url")
                        fetchAndProcess(url, minWordCount)
                    }
                }

                ContentAnalyzer.ContentType.PREVIEW -> {
                    // RSS is just a preview - fetch full article
                    Log.d(TAG, "RSS content is preview, fetching full article from: $url")
                    fetchAndProcess(url, minWordCount) ?: run {
                        // Fallback: use truncated RSS content if URL fetch fails
                        // This ensures we still get some content even if the site blocks scraping
                        Log.d(TAG, "URL fetch failed, falling back to RSS content for: $url")
                        processRssContent(
                            url = url,
                            htmlContent = rssContent ?: rssDescription ?: "",
                            rssTitle = rssTitle,
                            rssAuthor = rssAuthor,
                            minWordCount = 0  // Don't apply word count filter for fallback content
                        )
                    }
                }

                ContentAnalyzer.ContentType.UNCERTAIN -> {
                    // Try RSS content first, but be ready to fetch
                    val rssResult = processRssContent(
                        url = url,
                        htmlContent = rssContent ?: rssDescription ?: "",
                        rssTitle = rssTitle,
                        rssAuthor = rssAuthor,
                        minWordCount = minWordCount
                    )

                    if (rssResult != null && countWords(rssResult.content) >= MIN_RSS_CONTENT_WORDS) {
                        rssResult
                    } else {
                        Log.d(TAG, "RSS content insufficient (${rssResult?.let { countWords(it.content) } ?: 0} words), fetching from URL: $url")
                        fetchAndProcess(url, minWordCount) ?: rssResult
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error processing with RSS content for $url", e)
            // Fallback to direct URL fetch
            fetchAndProcess(url, minWordCount)
        }
    }

    /**
     * Processes RSS HTML content directly without fetching from URL.
     */
    private fun processRssContent(
        url: String,
        htmlContent: String,
        rssTitle: String?,
        rssAuthor: String?,
        minWordCount: Int
    ): ProcessedArticle? {
        if (htmlContent.isBlank()) return null

        // Clean and process the RSS content
        val cleanedContent = cleanRssContent(htmlContent)

        // Apply word count filter
        if (minWordCount > 0) {
            val wordCount = countWords(cleanedContent)
            if (wordCount < minWordCount) {
                return null
            }
        }

        // Use RSS title/author if available, otherwise try to extract
        val title = rssTitle?.trim()?.takeIf { it.isNotBlank() }
            ?: extractTitleFromContent(cleanedContent)
            ?: return null

        return ProcessedArticle(
            title = title,
            author = rssAuthor?.trim() ?: "",
            content = cleanedContent,
            originalUrl = url,
            isSummary = false
        )
    }

    /**
     * Cleans RSS content by removing "read more" links, tracking elements,
     * and normalizing HTML.
     */
    private fun cleanRssContent(html: String): String {
        val doc = Jsoup.parseBodyFragment(html)

        // Remove "read more" links at the end
        doc.select("a").toList().filter { anchor ->
            val text = anchor.text().lowercase()
            text.contains("read") && (text.contains("more") || text.contains("full") || text.contains("story")) ||
            text.contains("lesen") ||
            text.contains("continue") ||
            text.contains("weiterlesen")
        }.forEach { it.remove() }

        // Remove empty paragraphs that might be left after removing read more links
        doc.select("p").toList().filter { it.text().isBlank() }.forEach { it.remove() }

        // Remove tracking pixels and hidden images
        doc.select("img[width=1], img[height=1], img[src*='pixel'], img[src*='track']").remove()

        // Remove style and class attributes
        doc.select("[style]").removeAttr("style")
        doc.select("[class]").removeAttr("class")

        // Remove script/style tags
        doc.select("script, style, noscript").remove()

        // Remove common ad/tracking elements
        doc.select("[data-i13n], [data-type='product-list']").remove()

        return doc.body().html()
    }

    /**
     * Extracts title from content if not provided.
     */
    private fun extractTitleFromContent(html: String): String? {
        val doc = Jsoup.parseBodyFragment(html)
        return doc.select("h1, h2").firstOrNull()?.text()?.trim()
    }

    /**
     * Fetches and processes a URL to extract clean article content.
     * This is the original method, now used as fallback.
     *
     * @param url The URL to fetch and process
     * @param minWordCount Minimum word count threshold; articles below this are skipped
     * @return ProcessedArticle if successful, null if fetching/parsing fails or word count is below threshold
     */
    private suspend fun fetchAndProcess(
        url: String,
        minWordCount: Int = DEFAULT_MIN_WORD_COUNT
    ): ProcessedArticle? = withContext(Dispatchers.IO) {
        try {
            val document = fetchDocument(url)
            processDocument(url, document, minWordCount)
        } catch (e: Exception) {
            Log.e(TAG, "Error fetching from URL: $url", e)
            null
        }
    }

    /**
     * Legacy method: Fetches and processes a URL to extract clean article content.
     * Kept for backward compatibility but prefers processWithRssContent for smart fetching.
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
     * Includes browser-like headers to improve success rate with sites that block scrapers.
     */
    private fun fetchDocument(url: String): Document {
        // Extract domain for Referer header
        val referer = try {
            val uri = java.net.URI(url)
            "${uri.scheme}://${uri.host}/"
        } catch (e: Exception) {
            url
        }

        return Jsoup.connect(url)
            .userAgent(USER_AGENT)
            .timeout(DEFAULT_TIMEOUT_MS)
            .followRedirects(true)
            .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
            .header("Accept-Language", "en-US,en;q=0.9")
            .header("Accept-Encoding", "gzip, deflate")
            .header("DNT", "1")
            .header("Connection", "keep-alive")
            .header("Upgrade-Insecure-Requests", "1")
            .header("Referer", referer)
            .header("Sec-Fetch-Dest", "document")
            .header("Sec-Fetch-Mode", "navigate")
            .header("Sec-Fetch-Site", "same-origin")
            .header("Sec-Fetch-User", "?1")
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
        if (countWords(cleanedContent) < MIN_EXTRACTED_WORDS) {
            return null
        }
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
        // Check if html is valid before parsing
        if (html.isBlank()) return ""

        // Use Jsoup.parse to properly handle HTML
        val doc = Jsoup.parse(html)

        // Remove script and style tags (shouldn't be present, but safety measure)
        doc.select("script, style, noscript").remove()

        // Remove tracking pixels and hidden images
        doc.select("img[width=1], img[height=1], img[src*='pixel'], img[src*='track']").remove()

        // Remove style and class attributes
        doc.select("[style]").removeAttr("style")
        doc.select("[class]").removeAttr("class")

        // Get the body content - use text() if html() is empty (Readability sometimes returns text-only)
        var result = doc.body().html()
        if (result.isBlank()) {
            // Try getting the outerHtml of all children
            result = doc.body().children().joinToString("\n") { it.outerHtml() }
        }
        if (result.isBlank()) {
            // Last resort: wrap raw text in paragraph tags
            val text = doc.body().text()
            if (text.isNotBlank()) {
                result = "<p>$text</p>"
            }
        }

        return result
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
