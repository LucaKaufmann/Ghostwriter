package com.example.epilogue.data.repository

import android.util.Log
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.service.ContentProcessor
import com.example.epilogue.service.OpenAIService
import com.example.epilogue.service.PromotionalContentFilter
import com.example.epilogue.service.RssService
import com.example.epilogue.shared.delivery.ArticleDeliveryIdentity
import com.example.epilogue.shared.delivery.ArticleIdentityResult
import kotlinx.coroutines.CancellationException
import java.security.MessageDigest
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
    private val settingsRepository: SettingsRepository,
    private val promotionalFilter: PromotionalContentFilter,
    private val deliveryStore: ArticleDeliveryStore
) {
    companion object {
        private const val TAG = "ArticleRepository"
        private const val FILTER_REVISION = "android-filter-v1"
    }

    private val identity = ArticleDeliveryIdentity()

    private fun filterSignature(feed: Feed, minWordCount: Int): String {
        val value = "$FILTER_REVISION|minWords=$minWordCount|mode=${feed.mode.name}"
        return MessageDigest.getInstance("SHA-256").digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    /** Parses the available page before identity filtering, fair ordering, and the cap. */
    suspend fun ingestForGeneration(feed: Feed, runId: Long,
        regeneration: Boolean = false): FeedIngestionResult {
        val items = try {
            rssService.fetchFeedForGeneration(feed.url)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            return FeedIngestionResult(feed, 0, 0, emptyList(), emptyList(),
                emptyList(), 0, feedError = "fetch_failed")
        }
        val minWords = settingsRepository.getMinWordCount()
        val signature = filterSignature(feed, minWords)
        data class Candidate(val key: String, val index: Int, val item: com.prof18.rssparser.model.RssItem)
        val issues = mutableListOf<DeliveryIssue>()
        val seen = mutableSetOf<String>()
        val candidates = items.mapIndexedNotNull { index, item ->
            when (val parsed = identity.fromArticleLink(item.link)) {
                ArticleIdentityResult.Invalid -> {
                    issues += DeliveryIssue(null, "identity", "invalid_identity")
                    null
                }
                is ArticleIdentityResult.Valid -> if (seen.add(parsed.articleKey))
                    Candidate(parsed.articleKey, index, item) else null
            }
        }
        val persisted = deliveryStore.forFeed(feed.url)
        val eligible = candidates.filter { candidate ->
            val row = persisted[candidate.key]
            regeneration || (row?.state != "delivered" &&
                !(row?.state == "excluded" && row.filterSignature == signature))
        }.sortedWith(compareBy<Candidate> { persisted[it.key]?.lastAttemptSequence ?: 0L }
            .thenBy { it.index })
        val selected = if (feed.maxArticles == 0) eligible else eligible.take(feed.maxArticles)
        val deferred = eligible.size - selected.size
        deliveryStore.markAttempts(runId, selected.map { DeliveryIdentity(feed.url, it.key) },
            signature, regeneration)

        val delivered = mutableListOf<DeliveredArticle>()
        val excluded = mutableListOf<ExcludedArticle>()
        var fallbacks = 0
        for (candidate in selected) {
            val item = candidate.item
            val id = DeliveryIdentity(feed.url, candidate.key)
            try {
                val promotion = promotionalFilter.isPromotional(item.link, item.title,
                    item.content?.takeIf { it.isNotBlank() } ?:
                        item.description?.takeIf { it.isNotBlank() })
                if (promotion.isPromotional) {
                    excluded += ExcludedArticle(id, "promotional", signature)
                    continue
                }
                val processed = when (val result = contentProcessor.processForGeneration(
                    url = item.link!!, rssContent = item.content,
                    rssDescription = item.description, rssTitle = item.title,
                    rssAuthor = item.author, minWordCount = minWords)) {
                    is ContentProcessor.GenerationResult.Ready -> result.article
                    ContentProcessor.GenerationResult.TooShort -> {
                        excluded += ExcludedArticle(id, "content_too_short", signature)
                        continue
                    }
                    ContentProcessor.GenerationResult.Failed -> {
                        issues += DeliveryIssue(candidate.key, "extraction", "extract_failed")
                        continue
                    }
                }
                val output = when (feed.mode) {
                    ProcessingMode.FIDELITY -> processed
                    ProcessingMode.BRIEFING -> when (val summary = openAIService.summarizeArticle(processed)) {
                        is OpenAIService.ArticleSummaryResult.Summarized -> summary.article
                        OpenAIService.ArticleSummaryResult.Promotional -> {
                            excluded += ExcludedArticle(id, "model_promotional", signature)
                            continue
                        }
                        OpenAIService.ArticleSummaryResult.Failed -> {
                            fallbacks++
                            issues += DeliveryIssue(candidate.key, "summary", "full_article_fallback")
                            processed.copy(isSummary = false)
                        }
                    }
                }
                delivered += DeliveredArticle(id, output.copy(feedUrl = feed.url, feedName = feed.name),
                    signature)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                issues += DeliveryIssue(candidate.key, "processing", "process_failed")
            }
        }
        return FeedIngestionResult(feed, items.size, selected.size, delivered, excluded,
            issues, deferred, fallbackCount = fallbacks)
    }

    /**
     * Result of fetching articles for a single feed.
     */
    data class FeedResult(
        val feed: Feed,
        val articles: List<ProcessedArticle>,
        val errors: Int,
        val filtered: Int = 0
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
        Log.d(TAG, "Fetching articles from feed: ${feed.name} (${feed.url}), onlyNew=$onlyNew, lastFetched=${feed.lastFetched}")
        val minWordCount = settingsRepository.getMinWordCount()
        val since = if (onlyNew) feed.lastFetched else 0L

        var rssItems = rssService.fetchNewArticles(feed.url, since)
        Log.d(TAG, "Feed ${feed.name}: got ${rssItems.size} RSS items after date filter (since=$since)")

        // Filter out promotional content before processing
        val nonPromotionalItems = rssItems.filter { item ->
            val filterResult = promotionalFilter.isPromotional(
                url = item.link,
                title = item.title,
                content = item.content ?: item.description
            )
            !filterResult.isPromotional
        }
        Log.d(TAG, "Feed ${feed.name}: filtered ${rssItems.size - nonPromotionalItems.size} promotional items")
        var filteredCount = rssItems.size - nonPromotionalItems.size
        rssItems = nonPromotionalItems

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
                    when (val summary = openAIService.summarizeArticle(processed)) {
                        is OpenAIService.ArticleSummaryResult.Summarized -> summary.article
                        OpenAIService.ArticleSummaryResult.Promotional -> {
                            filteredCount++
                            return@mapNotNull null
                        }
                        OpenAIService.ArticleSummaryResult.Failed -> {
                            errorCount++
                            // Preserve the full-article fallback for provider/configuration errors.
                            processed.copy(isSummary = false)
                        }
                    }
                }
            }.copy(
                feedUrl = feed.url,
                feedName = feed.name
            )
        }

        // Update lastFetched timestamp
        if (articles.isNotEmpty()) {
            feedRepository.updateLastFetched(feed.url, System.currentTimeMillis())
        }

        Log.d(TAG, "Feed ${feed.name}: processed ${articles.size} articles successfully, $errorCount errors")
        return FeedResult(feed, articles, errorCount, filteredCount)
    }

    /**
     * Fetches and processes articles from all feeds.
     * Processes feeds in parallel for efficiency.
     *
     * @param feeds List of feeds to fetch from
     * @param onlyNew If true, only fetch articles published after lastFetched
     * @return List of all processed articles, grouped by feed
     */
    suspend fun fetchAllArticles(
        feeds: List<Feed>,
        onlyNew: Boolean = true
    ): List<ProcessedArticle> = coroutineScope {
        Log.d(TAG, "Fetching articles from ${feeds.size} feeds, onlyNew=$onlyNew")

        val results = feeds.map { feed ->
            async { fetchArticles(feed, onlyNew) }
        }.awaitAll()

        // Combine all articles in feed order so each feed's articles stay together
        val allArticles = results.flatMap { it.articles }

        Log.d(TAG, "Total articles from all feeds: ${allArticles.size}")
        results.forEach { result ->
            Log.d(TAG, "  - ${result.feed.name}: ${result.articles.size} articles, ${result.errors} errors")
        }

        allArticles
    }

    /**
     * Fetches articles from all saved feeds.
     * Per-feed max article limits are applied in fetchArticles().
     *
     * @param onlyNew If true, only fetch new articles
     * @return List of all processed articles
     */
    suspend fun fetchFromAllFeeds(onlyNew: Boolean = true): List<ProcessedArticle> {
        val feeds = feedRepository.getEnabledFeedsList()
        return fetchAllArticles(feeds, onlyNew)
    }
}
