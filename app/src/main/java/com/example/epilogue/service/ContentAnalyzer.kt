package com.example.epilogue.service

import org.jsoup.Jsoup
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Analyzes RSS/Atom feed content to determine if it contains full articles
 * or just previews that require fetching from the original URL.
 *
 * Many RSS feeds only include truncated previews with "Read more" links.
 * This analyzer detects such patterns to enable smart fetching.
 */
@Singleton
class ContentAnalyzer @Inject constructor() {

    companion object {
        // Minimum word count to consider content "full" (not a preview)
        private const val MIN_FULL_ARTICLE_WORDS = 200

        // Maximum word count for content that's definitely a preview
        private const val MAX_PREVIEW_WORDS = 100

        // Common "read more" patterns in various languages
        private val READ_MORE_PATTERNS = listOf(
            // English patterns
            Regex("""Read\s+(the\s+)?full\s+(story|article|post)""", RegexOption.IGNORE_CASE),
            Regex("""Continue\s+reading""", RegexOption.IGNORE_CASE),
            Regex("""Read\s+more""", RegexOption.IGNORE_CASE),
            Regex("""See\s+(the\s+)?full\s+(story|article|post)""", RegexOption.IGNORE_CASE),
            Regex("""Click\s+(here\s+)?(to\s+)?read""", RegexOption.IGNORE_CASE),
            Regex("""View\s+(the\s+)?full\s+(article|post)""", RegexOption.IGNORE_CASE),
            Regex("""\[\s*\.\.\.\s*\]"""),  // [...]
            Regex("""\.{3,}\s*$"""),  // ... at end
            Regex("""…\s*$"""),  // ellipsis at end

            // German patterns
            Regex("""\(Auf\s+.+\s+lesen\)""", RegexOption.IGNORE_CASE),
            Regex("""Weiterlesen""", RegexOption.IGNORE_CASE),
            Regex("""Mehr\s+lesen""", RegexOption.IGNORE_CASE),
            Regex("""Zum\s+(vollständigen\s+)?Artikel""", RegexOption.IGNORE_CASE),

            // French patterns
            Regex("""Lire\s+la\s+suite""", RegexOption.IGNORE_CASE),
            Regex("""Lire\s+l'article""", RegexOption.IGNORE_CASE),

            // Spanish patterns
            Regex("""Leer\s+más""", RegexOption.IGNORE_CASE),
            Regex("""Seguir\s+leyendo""", RegexOption.IGNORE_CASE),

            // Generic patterns
            Regex("""This\s+article\s+originally\s+appeared""", RegexOption.IGNORE_CASE)
        )

        // Patterns indicating content was truncated mid-sentence
        private val TRUNCATION_INDICATORS = listOf(
            Regex("""\s+…\s*</p>\s*$""", RegexOption.IGNORE_CASE),
            Regex("""\s+\.\.\.\s*</p>\s*$""", RegexOption.IGNORE_CASE),
            Regex("""\s+–\s*$"""),  // en-dash at end
            Regex("""\s+-\s*$"""),  // hyphen at end
            Regex("""[a-z],\s*$""", RegexOption.IGNORE_CASE),  // ends with comma
        )
    }

    /**
     * Result of content analysis
     */
    data class AnalysisResult(
        val contentType: ContentType,
        val wordCount: Int,
        val hasReadMoreLink: Boolean,
        val isTruncated: Boolean,
        val extractedText: String,
        val confidence: Float  // 0.0 to 1.0
    )

    enum class ContentType {
        /** Content appears to be a full article - use as-is */
        FULL_ARTICLE,

        /** Content is clearly a preview - must fetch from URL */
        PREVIEW,

        /** Uncertain - try RSS content first, fetch if inadequate */
        UNCERTAIN
    }

    /**
     * Analyzes RSS item content to determine if it's a full article or preview.
     *
     * @param content The HTML content from RSS item (content:encoded or description)
     * @param description Optional description/summary field
     * @return AnalysisResult with content type and metadata
     */
    fun analyze(content: String?, description: String?): AnalysisResult {
        // Use content if available, fall back to description
        val htmlContent = content?.takeIf { it.isNotBlank() }
            ?: description?.takeIf { it.isNotBlank() }
            ?: return AnalysisResult(
                contentType = ContentType.PREVIEW,
                wordCount = 0,
                hasReadMoreLink = false,
                isTruncated = false,
                extractedText = "",
                confidence = 1.0f
            )

        val extractedText = extractText(htmlContent)
        val wordCount = countWords(extractedText)
        val hasReadMoreLink = detectReadMorePattern(htmlContent)
        val isTruncated = detectTruncation(htmlContent, extractedText)

        val (contentType, confidence) = determineContentType(
            wordCount = wordCount,
            hasReadMoreLink = hasReadMoreLink,
            isTruncated = isTruncated,
            htmlContent = htmlContent
        )

        return AnalysisResult(
            contentType = contentType,
            wordCount = wordCount,
            hasReadMoreLink = hasReadMoreLink,
            isTruncated = isTruncated,
            extractedText = extractedText,
            confidence = confidence
        )
    }

    /**
     * Quick check if content is likely a preview (for performance).
     * Use full analyze() for detailed analysis.
     */
    fun isLikelyPreview(content: String?, description: String?): Boolean {
        val htmlContent = content?.takeIf { it.isNotBlank() }
            ?: description?.takeIf { it.isNotBlank() }
            ?: return true

        // Quick checks
        val wordCount = countWords(extractText(htmlContent))
        if (wordCount < MAX_PREVIEW_WORDS) return true

        // Check for obvious read more patterns
        return READ_MORE_PATTERNS.any { it.containsMatchIn(htmlContent) }
    }

    /**
     * Extracts clean text from HTML content.
     */
    private fun extractText(html: String): String {
        return try {
            Jsoup.parse(html).text()
        } catch (e: Exception) {
            html.replace(Regex("<[^>]+>"), " ")
                .replace(Regex("\\s+"), " ")
                .trim()
        }
    }

    /**
     * Counts words in text.
     */
    private fun countWords(text: String): Int {
        return text.split(Regex("\\s+"))
            .filter { it.isNotBlank() && it.length > 1 }
            .size
    }

    /**
     * Detects "read more" or "continue reading" patterns.
     */
    private fun detectReadMorePattern(html: String): Boolean {
        return READ_MORE_PATTERNS.any { pattern ->
            pattern.containsMatchIn(html)
        }
    }

    /**
     * Detects if content appears truncated mid-sentence.
     */
    private fun detectTruncation(html: String, text: String): Boolean {
        // Check HTML for truncation patterns
        if (TRUNCATION_INDICATORS.any { it.containsMatchIn(html) }) {
            return true
        }

        // Check if text ends abruptly (no proper sentence ending)
        val trimmedText = text.trim()
        if (trimmedText.isNotEmpty()) {
            val lastChar = trimmedText.last()
            // Normal endings: . ! ? " ' ) ]
            val normalEndings = setOf('.', '!', '?', '"', '\'', ')', ']', '。', '！', '？')
            if (lastChar !in normalEndings && trimmedText.length > 50) {
                // Content ends without proper punctuation - might be truncated
                return true
            }
        }

        return false
    }

    /**
     * Determines content type based on all signals.
     */
    private fun determineContentType(
        wordCount: Int,
        hasReadMoreLink: Boolean,
        isTruncated: Boolean,
        htmlContent: String
    ): Pair<ContentType, Float> {
        // Strong signals for preview
        if (hasReadMoreLink) {
            return ContentType.PREVIEW to 0.95f
        }

        if (wordCount < MAX_PREVIEW_WORDS) {
            return ContentType.PREVIEW to 0.9f
        }

        if (isTruncated && wordCount < MIN_FULL_ARTICLE_WORDS) {
            return ContentType.PREVIEW to 0.85f
        }

        // Strong signals for full article
        if (wordCount >= MIN_FULL_ARTICLE_WORDS && !isTruncated && !hasReadMoreLink) {
            // Check for article structure (multiple paragraphs)
            val paragraphCount = Jsoup.parse(htmlContent).select("p").size
            if (paragraphCount >= 3) {
                return ContentType.FULL_ARTICLE to 0.9f
            }
            return ContentType.FULL_ARTICLE to 0.75f
        }

        // Uncertain cases
        if (wordCount in MAX_PREVIEW_WORDS until MIN_FULL_ARTICLE_WORDS) {
            return if (isTruncated) {
                ContentType.PREVIEW to 0.7f
            } else {
                ContentType.UNCERTAIN to 0.5f
            }
        }

        return ContentType.UNCERTAIN to 0.5f
    }

    /**
     * Extracts the article link from "read more" anchor if present.
     * This can be useful when the RSS item link differs from the actual article URL.
     */
    fun extractReadMoreUrl(html: String): String? {
        val doc = Jsoup.parse(html)

        // Look for anchors with "read more" text
        val readMoreAnchors = doc.select("a").filter { anchor ->
            val text = anchor.text()
            val href = anchor.attr("href")
            href.isNotBlank() && READ_MORE_PATTERNS.any { it.containsMatchIn(text) }
        }

        return readMoreAnchors.firstOrNull()?.attr("href")
    }
}
