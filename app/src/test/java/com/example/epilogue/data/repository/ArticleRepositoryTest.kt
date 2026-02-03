package com.example.epilogue.data.repository

import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.service.ContentProcessor
import com.example.epilogue.service.OpenAIService
import com.example.epilogue.service.PromotionalContentFilter
import com.example.epilogue.service.RssService
import com.prof18.rssparser.model.RssItem
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.spyk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ArticleRepositoryTest {

    private val rssService: RssService = mockk()
    private val contentProcessor: ContentProcessor = mockk()
    private val openAIService: OpenAIService = mockk()
    private val feedRepository: FeedRepository = mockk(relaxed = true)
    private val settingsRepository: SettingsRepository = mockk()
    private val promotionalFilter: PromotionalContentFilter = mockk()

    private val repository = ArticleRepository(
        rssService,
        contentProcessor,
        openAIService,
        feedRepository,
        settingsRepository,
        promotionalFilter
    )

    @Test
    fun `fetchArticles filters promotional items and updates lastFetched`() = runTest {
        val feed = Feed(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.FIDELITY,
            lastFetched = 123L
        )

        val item1 = mockRssItem(
            link = "https://example.com/article",
            title = "Article",
            content = "<p>Content</p>",
            description = "<p>Desc</p>",
            author = "Author"
        )
        val item2 = mockRssItem(
            link = "https://example.com/deals",
            title = "Deal",
            content = "<p>Promo</p>",
            description = null,
            author = null
        )

        every { settingsRepository.getMinWordCount() } returns 0
        coEvery { rssService.fetchNewArticles(any(), any()) } returns listOf(item1, item2)

        every { promotionalFilter.isPromotional(any(), any(), any()) } answers {
            val url = firstArg<String?>() ?: ""
            PromotionalContentFilter.FilterResult(isPromotional = url.contains("deals"))
        }

        val processed = ProcessedArticle(
            title = "Article",
            author = "Author",
            content = "<p>Content</p>",
            originalUrl = "https://example.com/article",
            isSummary = false
        )

        coEvery { contentProcessor.processWithRssContent(any(), any(), any(), any(), any(), any()) } returns processed

        val result = repository.fetchArticles(feed, onlyNew = true)

        assertEquals(1, result.articles.size)
        assertEquals(processed, result.articles.first())
        coVerify { feedRepository.updateLastFetched(feed.url, any()) }
        coVerify(exactly = 1) { contentProcessor.processWithRssContent(any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `fetchArticles respects maxArticles limit`() = runTest {
        val feed = Feed(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.FIDELITY,
            lastFetched = 0L,
            maxArticles = 1
        )

        val item1 = mockRssItem("https://example.com/a", "A", "<p>A</p>", null, null)
        val item2 = mockRssItem("https://example.com/b", "B", "<p>B</p>", null, null)

        every { settingsRepository.getMinWordCount() } returns 0
        coEvery { rssService.fetchNewArticles(feed.url, 0L) } returns listOf(item1, item2)
        every { promotionalFilter.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(isPromotional = false)

        coEvery { contentProcessor.processWithRssContent(any(), any(), any(), any(), any(), any()) } returns
            ProcessedArticle("A", "", "<p>A</p>", "https://example.com/a", false)

        val result = repository.fetchArticles(feed, onlyNew = true)

        assertEquals(1, result.articles.size)
        coVerify(exactly = 1) { contentProcessor.processWithRssContent(any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `fetchArticles falls back to full article when summarization fails`() = runTest {
        val feed = Feed(
            url = "https://example.com/rss",
            name = "Example",
            mode = ProcessingMode.BRIEFING
        )

        val item = mockRssItem("https://example.com/a", "A", "<p>A</p>", null, null)
        every { settingsRepository.getMinWordCount() } returns 0
        coEvery { rssService.fetchNewArticles(feed.url, 0L) } returns listOf(item)
        every { promotionalFilter.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(isPromotional = false)

        val processed = ProcessedArticle("A", "", "<p>A</p>", "https://example.com/a", false)
        coEvery { contentProcessor.processWithRssContent(any(), any(), any(), any(), any(), any()) } returns processed
        coEvery { openAIService.summarizeArticle(processed) } returns null

        val result = repository.fetchArticles(feed, onlyNew = true)

        assertEquals(1, result.articles.size)
        assertFalse(result.articles.first().isSummary)
        assertEquals(1, result.errors)
    }

    @Test
    fun `fetchAllArticles sorts summaries first`() = runTest {
        val feedA = Feed("https://example.com/a", "A", ProcessingMode.BRIEFING)
        val feedB = Feed("https://example.com/b", "B", ProcessingMode.FIDELITY)

        val summary = ProcessedArticle("Summary", "", "<p>Summary</p>", "https://example.com/summary", true)
        val full = ProcessedArticle("Full", "", "<p>Full</p>", "https://example.com/full", false)

        val spyRepo = spyk(repository)
        coEvery { spyRepo.fetchArticles(feedA, any()) } returns
            ArticleRepository.FeedResult(feedA, listOf(full, summary), 0)
        coEvery { spyRepo.fetchArticles(feedB, any()) } returns
            ArticleRepository.FeedResult(feedB, listOf(full), 0)

        val result = spyRepo.fetchAllArticles(listOf(feedA, feedB), onlyNew = true)

        assertTrue(result.first().isSummary)
        assertEquals(3, result.size)
    }

    private fun mockRssItem(
        link: String?,
        title: String?,
        content: String?,
        description: String?,
        author: String?
    ): RssItem {
        val item = mockk<RssItem>()
        every { item.link } returns link
        every { item.title } returns title
        every { item.content } returns content
        every { item.description } returns description
        every { item.author } returns author
        return item
    }
}
