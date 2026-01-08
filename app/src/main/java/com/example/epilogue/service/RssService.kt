package com.example.epilogue.service

import android.util.Log
import com.prof18.rssparser.RssParser
import com.prof18.rssparser.model.RssItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Service for fetching and parsing RSS/Atom feeds.
 */
@Singleton
class RssService @Inject constructor() {

    companion object {
        private const val TAG = "RssService"
    }

    private val parser = RssParser()

    /**
     * Fetches articles from an RSS/Atom feed URL.
     *
     * @param feedUrl The URL of the RSS/Atom feed
     * @return List of RssItems, or empty list if fetching fails
     */
    suspend fun fetchFeed(feedUrl: String): List<RssItem> = withContext(Dispatchers.IO) {
        try {
            val channel = parser.getRssChannel(feedUrl)
            Log.d(TAG, "Fetched ${channel.items.size} items from $feedUrl")
            channel.items
        } catch (e: Exception) {
            Log.e(TAG, "Failed to fetch feed $feedUrl: ${e.message}")
            emptyList()
        }
    }

    /**
     * Fetches articles from a feed, filtered by publish date.
     *
     * @param feedUrl The URL of the RSS/Atom feed
     * @param since Only return articles published after this timestamp (millis)
     * @return List of RssItems published after the given timestamp
     */
    suspend fun fetchNewArticles(feedUrl: String, since: Long): List<RssItem> {
        val items = fetchFeed(feedUrl)
        if (since <= 0) return items

        return items.filter { item ->
            val pubDate = item.pubDate?.let { parseDate(it) } ?: 0L
            // Include articles with unparseable/missing dates (0L) as they might be new
            pubDate == 0L || pubDate > since
        }
    }

    /**
     * Validates that a URL is a valid RSS/Atom feed.
     *
     * @param feedUrl The URL to validate
     * @return true if the URL returns a valid feed
     */
    suspend fun validateFeed(feedUrl: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val channel = parser.getRssChannel(feedUrl)
            channel.items.isNotEmpty() || channel.title != null
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Parses various date formats commonly used in RSS feeds.
     */
    private fun parseDate(dateString: String): Long {
        val formats = listOf(
            java.text.SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss Z", java.util.Locale.US),
            java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", java.util.Locale.US),
            java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", java.util.Locale.US),
            java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", java.util.Locale.US),
            java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.US)
        )

        for (format in formats) {
            try {
                return format.parse(dateString)?.time ?: continue
            } catch (e: Exception) {
                continue
            }
        }

        return 0L
    }
}
