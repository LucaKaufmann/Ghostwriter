package com.example.epilogue.service

import android.util.Log
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Filters out promotional and deal-focused content from RSS feeds.
 * Detects articles that are primarily advertisements or affiliate marketing
 * based on URL patterns, title keywords, and content markers.
 */
@Singleton
class PromotionalContentFilter @Inject constructor() {

    companion object {
        private const val TAG = "PromotionalContentFilter"

        // URL path segments that indicate deals/promotions
        private val PROMOTIONAL_URL_SEGMENTS = setOf(
            "/deals/",
            "/deal/",
            "/offers/",
            "/offer/",
            "/promo/",
            "/promotions/",
            "/sale/",
            "/sales/",
            "/discount/",
            "/discounts/",
            "/coupon/",
            "/coupons/",
            "/affiliate/",
            "/sponsored/"
        )

        // Title patterns indicating promotional content (case-insensitive)
        private val PROMOTIONAL_TITLE_PATTERNS = listOf(
            Regex("""(\d+)\s*(%|percent)\s*off""", RegexOption.IGNORE_CASE),
            Regex("""(is|are|now|just|only)\s*\$\d+""", RegexOption.IGNORE_CASE),
            Regex("""for\s*(just|only)\s*\$\d+""", RegexOption.IGNORE_CASE),
            Regex("""\$\d+\s*(off|discount)""", RegexOption.IGNORE_CASE),
            Regex("""save\s*\$\d+""", RegexOption.IGNORE_CASE),
            Regex("""(lowest|best|cheapest)\s*price""", RegexOption.IGNORE_CASE),
            Regex("""(deal|deals|sale|promo)\s*(of the|alert|:)""", RegexOption.IGNORE_CASE),
            Regex("""(flash|lightning)\s*sale""", RegexOption.IGNORE_CASE),
            Regex("""(limited time|today only|ends soon)""", RegexOption.IGNORE_CASE),
            Regex("""(black friday|cyber monday|prime day)""", RegexOption.IGNORE_CASE),
            Regex("""you can (get|grab|snag|score).*\$\d+""", RegexOption.IGNORE_CASE),
            Regex("""drops to\s*\$\d+""", RegexOption.IGNORE_CASE),
            Regex("""at its lowest""", RegexOption.IGNORE_CASE),
            Regex("""all-time low""", RegexOption.IGNORE_CASE)
        )

        // Content markers that strongly indicate promotional content
        private val PROMOTIONAL_CONTENT_MARKERS = listOf(
            "elm:affiliate_link",
            "data-type=\"product-list\"",
            "<core-commerce",
            "use code ",
            "coupon code",
            "promo code",
            "discount code",
            "@EngadgetDeals",
            "Follow @",
            "for the latest tech deals"
        )
    }

    /**
     * Result of promotional content detection.
     */
    data class FilterResult(
        val isPromotional: Boolean,
        val reason: String? = null,
        val confidence: Float = 0f
    )

    /**
     * Checks if an RSS item appears to be promotional content.
     *
     * @param url The article URL
     * @param title The article title
     * @param content The RSS content/description (HTML)
     * @return FilterResult indicating if the content is promotional
     */
    fun isPromotional(
        url: String?,
        title: String?,
        content: String?
    ): FilterResult {
        var score = 0f
        var reason: String? = null

        // Check URL patterns (strong signal)
        if (url != null) {
            val urlLower = url.lowercase()
            for (segment in PROMOTIONAL_URL_SEGMENTS) {
                if (urlLower.contains(segment)) {
                    score += 0.6f
                    reason = "URL contains promotional segment: $segment"
                    Log.d(TAG, "URL match: $segment in $url")
                    break
                }
            }
        }

        // Check title patterns (strong signal)
        if (title != null) {
            for (pattern in PROMOTIONAL_TITLE_PATTERNS) {
                if (pattern.containsMatchIn(title)) {
                    score += 0.5f
                    reason = reason ?: "Title matches promotional pattern: ${pattern.pattern}"
                    Log.d(TAG, "Title match: ${pattern.pattern} in '$title'")
                    break
                }
            }
        }

        // Check content markers (medium signal)
        if (content != null) {
            val contentLower = content.lowercase()
            var contentMatches = 0
            for (marker in PROMOTIONAL_CONTENT_MARKERS) {
                if (contentLower.contains(marker.lowercase())) {
                    contentMatches++
                    Log.d(TAG, "Content marker found: $marker")
                }
            }
            if (contentMatches > 0) {
                // Scale by number of matches found
                val contentScore = minOf(0.4f * contentMatches, 0.8f)
                score += contentScore
                reason = reason ?: "Content contains $contentMatches promotional markers"
            }
        }

        val isPromotional = score >= 0.5f

        if (isPromotional) {
            Log.i(TAG, "Filtered promotional content: '$title' (score=$score, reason=$reason)")
        }

        return FilterResult(
            isPromotional = isPromotional,
            reason = reason,
            confidence = minOf(score, 1f)
        )
    }
}
