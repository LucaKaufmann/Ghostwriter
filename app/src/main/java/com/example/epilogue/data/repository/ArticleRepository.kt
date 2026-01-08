package com.example.epilogue.data.repository

import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.service.ContentProcessor
import com.example.epilogue.service.OpenAIService
import com.example.epilogue.service.RssService
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for fetching and processing articles from RSS feeds.
 * Orchestrates RSS fetching, content extraction, and AI summarization.
 */
@Singleton
class ArticleRepository @Inject constructor(
    private val rssService: RssService,
    private val contentProcessor: ContentProcessor,
    private val openAIService: OpenAIService,
    private val feedRepository: FeedRepository,
    private val settingsRepository: SettingsRepository
) {

    /**
     * Result of fetching articles for a single feed.
     */
    data class FeedResult(
        val feed: Feed,
        val articles: List<ProcessedArticle>,
        val errors: Int
    )

    /**
     * Fetches and processes articles from a single feed.
     *
     * Uses smart fetching: analyzes RSS content to determine if it contains
     * the full article or just a preview. Only fetches from the URL when
     * the RSS content is a preview, saving bandwidth and time.
     *
     * @param feed The feed to fetch from
     * @param onlyNew If true, only fetch articles published after lastFetched
     * @return FeedResult containing processed articles
     */
    suspend fun fetchArticles(feed: Feed, onlyNew: Boolean = true): FeedResult {
        val minWordCount = settingsRepository.getMinWordCount()
        val since = if (onlyNew) feed.lastFetched else 0L

        var rssItems = rssService.fetchNewArticles(feed.url, since)

        // Apply per-feed max articles limit before processing
        if (feed.maxArticles > 0) {
            rssItems = rssItems.take(feed.maxArticles)
        }

        var errorCount = 0

        val articles = rssItems.mapNotNull { item ->
            val link = item.link ?: return@mapNotNull null

            // Use smart fetching: analyze RSS content before deciding to fetch from URL
            // This saves HTTP requests when RSS already contains the full article
            val processed = contentProcessor.processWithRssContent(
                url = link,
                rssContent = item.content,
                rssDescription = item.description,
                rssTitle = item.title,
                rssAuthor = item.author,
                minWordCount = minWordCount
            ) ?: run {
                errorCount++
                return@mapNotNull null
            }

            // Apply processing mode
            when (feed.mode) {
                ProcessingMode.FIDELITY -> processed
                ProcessingMode.BRIEFING -> {
                    openAIService.summarizeArticle(processed) ?: run {
                        errorCount++
                        // Fall back to full article if summarization fails
                        processed.copy(isSummary = false)
                    }
                }
            }
        }

        // Update lastFetched timestamp
        if (articles.isNotEmpty()) {
            feedRepository.updateLastFetched(feed.url, System.currentTimeMillis())
        }

        return FeedResult(feed, articles, errorCount)
    }

    /**
     * Fetches and processes articles from all feeds.
     * Processes feeds in parallel for efficiency.
     *
     * @param feeds List of feeds to fetch from
     * @param onlyNew If true, only fetch articles published after lastFetched
     * @return List of all processed articles, sorted with summaries first
     */
    suspend fun fetchAllArticles(
        feeds: List<Feed>,
        onlyNew: Boolean = true
    ): List<ProcessedArticle> = coroutineScope {
        val results = feeds.map { feed ->
            async { fetchArticles(feed, onlyNew) }
        }.awaitAll()

        // Combine all articles, summaries first
        val allArticles = results.flatMap { it.articles }

        allArticles.sortedByDescending { it.isSummary }
    }

    /**
     * Fetches articles from all saved feeds.
     * Per-feed max article limits are applied in fetchArticles().
     *
     * @param onlyNew If true, only fetch new articles
     * @return List of all processed articles
     */
    suspend fun fetchFromAllFeeds(onlyNew: Boolean = true): List<ProcessedArticle> {
        val feeds = feedRepository.getAllFeedsList()
        return fetchAllArticles(feeds, onlyNew)
    }
}
