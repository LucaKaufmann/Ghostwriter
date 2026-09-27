package com.example.epilogue.data.repository

import com.example.epilogue.data.remote.openai.ChatCompletionResponse
import com.example.epilogue.data.remote.openai.ChatMessage
import com.example.epilogue.data.remote.openai.Choice
import com.example.epilogue.data.remote.openai.OpenAIApi
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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import java.io.IOException

/** Actual summary service and repository with synthetic source/provider boundaries. */
class ArticleRepositoryTest {
    private val api = mockk<OpenAIApi>()
    private val settings = mockk<SettingsRepository>()
    private val rss = mockk<RssService>()
    private val processor = mockk<ContentProcessor>()
    private val feeds = mockk<FeedRepository>(relaxed = true)
    private val filter = mockk<PromotionalContentFilter>()
    private val deliveryStore = mockk<ArticleDeliveryStore>()
    private val feed = Feed("https://example.test/feed", "Fixture", ProcessingMode.BRIEFING)
    private val original = ProcessedArticle(
        "Article", "Author", "<p>Original body</p>", "https://example.test/article", false,
        publishedAt = 1234, wordCount = 400
    )
    private lateinit var repository: ArticleRepository

    @Before fun setUp() {
        every { settings.getMinWordCount() } returns 300
        every { settings.getOpenAIApiKey() } returns "fixture-key"
        val item = mockk<RssItem>(relaxed = true)
        every { item.link } returns original.originalUrl
        every { item.title } returns original.title
        every { item.content } returns original.content
        every { item.description } returns null
        every { item.author } returns original.author
        coEvery { rss.fetchNewArticles(feed.url, any()) } returns listOf(item)
        every { filter.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(false)
        coEvery { processor.processWithRssContent(any(), any(), any(), any(), any(), any()) } returns original
        repository = ArticleRepository(rss, processor, OpenAIService(api, settings), feeds, settings, filter, deliveryStore)
    }

    private fun response(content: String) = Response.success(ChatCompletionResponse(
        id = "fixture", choices = listOf(Choice(0, ChatMessage("assistant", content), "stop")), usage = null
    ))

    @Test fun `promotional sentinel never becomes fallback content or AI failure`() = runTest {
        coEvery { api.createChatCompletion(any(), any()) } returns response("  promotional_CONTENT \n")
        val result = repository.fetchArticles(feed)
        assertTrue(result.articles.isEmpty())
        assertEquals(1, result.filtered)
        assertEquals(0, result.errors)
        coVerify(exactly = 0) { feeds.updateLastFetched(any(), any()) }
    }

    @Test fun `HTTP provider failure retains full article and reports an error`() = runTest {
        coEvery { api.createChatCompletion(any(), any()) } returns Response.error(503, "Unavailable".toResponseBody())
        assertFallback(repository.fetchArticles(feed))
    }

    @Test fun `network failure retains full article and reports an error`() = runTest {
        coEvery { api.createChatCompletion(any(), any()) } throws IOException("fixture failure")
        assertFallback(repository.fetchArticles(feed))
    }

    @Test fun `missing key retains full article without a provider call`() = runTest {
        every { settings.getOpenAIApiKey() } returns null
        assertFallback(repository.fetchArticles(feed))
        coVerify(exactly = 0) { api.createChatCompletion(any(), any()) }
    }

    @Test fun `successful summary retains source identity and is not filtered`() = runTest {
        coEvery { api.createChatCompletion(any(), any()) } returns response("**Hook**: A summary.")
        val result = repository.fetchArticles(feed)
        val article = result.articles.single()
        assertTrue(article.isSummary)
        assertEquals("<p><strong>Hook</strong>: A summary.</p>", article.content)
        assertEquals(feed.url, article.feedUrl)
        assertEquals(original.originalUrl, article.originalUrl)
        assertEquals(0, result.filtered)
        assertEquals(0, result.errors)
    }

    @Test fun `fidelity keeps full article without consulting summarizer`() = runTest {
        val result = repository.fetchArticles(feed.copy(mode = ProcessingMode.FIDELITY))
        assertEquals(original.content, result.articles.single().content)
        assertFalse(result.articles.single().isSummary)
        assertEquals(0, result.errors)
        assertEquals(0, result.filtered)
        coVerify(exactly = 0) { api.createChatCompletion(any(), any()) }
    }

    @Test fun `cancellation propagates without fallback or progress acknowledgement`() = runTest {
        val cancellation = CancellationException("fixture cancellation")
        coEvery { api.createChatCompletion(any(), any()) } throws cancellation
        try {
            repository.fetchArticles(feed)
            fail("Cancellation must propagate")
        } catch (actual: CancellationException) {
            assertEquals(cancellation.message, actual.message)
        }
        coVerify(exactly = 0) { feeds.updateLastFetched(any(), any()) }
    }

    private fun assertFallback(result: ArticleRepository.FeedResult) {
        assertEquals(original.content, result.articles.single().content)
        assertFalse(result.articles.single().isSummary)
        assertEquals(1, result.errors)
        assertEquals(0, result.filtered)
    }
}
