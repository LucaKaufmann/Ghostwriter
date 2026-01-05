package com.example.epilog.data.repository

import com.example.epilog.domain.model.Feed
import com.example.epilog.domain.model.ProcessedArticle
import com.example.epilog.domain.model.ProcessingMode
import com.example.epilog.service.ContentProcessor
import com.example.epilog.service.OpenAIService
import com.example.epilog.service.RssService
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
     * @param feed The feed to fetch from
     * @param onlyNew If true, only fetch articles published after lastFetched
     * @return FeedResult containing processed articles
     */
    suspend fun fetchArticles(feed: Feed, onlyNew: Boolean = true): FeedResult {
        val minWordCount = settingsRepository.getMinWordCount()
        val since = if (onlyNew) feed.lastFetched else 0L

        val rssItems = rssService.fetchNewArticles(feed.url, since)
        var errorCount = 0

        val articles = rssItems.mapNotNull { item ->
            val link = item.link ?: return@mapNotNull null

            // Extract full content
            val processed = contentProcessor.process(link, minWordCount)
                ?: run {
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
     *
     * @param onlyNew If true, only fetch new articles
     * @return List of all processed articles
     */
    suspend fun fetchFromAllFeeds(onlyNew: Boolean = true): List<ProcessedArticle> {
        val feeds = feedRepository.getAllFeedsList()
        return fetchAllArticles(feeds, onlyNew)
    }
}
