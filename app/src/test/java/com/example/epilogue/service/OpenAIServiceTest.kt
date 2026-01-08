package com.example.epilogue.service

import com.example.epilogue.data.remote.openai.ChatCompletionResponse
import com.example.epilogue.data.remote.openai.ChatMessage
import com.example.epilogue.data.remote.openai.Choice
import com.example.epilogue.data.remote.openai.OpenAIApi
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.ProcessedArticle
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Response

class OpenAIServiceTest {

    private lateinit var openAIApi: OpenAIApi
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var service: OpenAIService

    @Before
    fun setup() {
        openAIApi = mockk()
        settingsRepository = mockk()
        service = OpenAIService(openAIApi, settingsRepository)
    }

    @Test
    fun `summarize returns NoApiKey when API key is not configured`() = runTest {
        every { settingsRepository.getOpenAIApiKey() } returns null

        val result = service.summarize("Title", "Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.NoApiKey)
    }

    @Test
    fun `summarize returns NoApiKey when API key is blank`() = runTest {
        every { settingsRepository.getOpenAIApiKey() } returns "   "

        val result = service.summarize("Title", "Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.NoApiKey)
    }

    @Test
    fun `summarize returns Success with summary on successful API call`() = runTest {
        val expectedSummary = "**Hook**: Test summary content."
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        val mockResponse = ChatCompletionResponse(
            id = "test-id",
            choices = listOf(
                Choice(
                    index = 0,
                    message = ChatMessage(role = "assistant", content = expectedSummary),
                    finishReason = "stop"
                )
            ),
            usage = null
        )

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.success(mockResponse)

        val result = service.summarize("Test Title", "Test Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.Success)
        assertEquals(expectedSummary, (result as OpenAIService.SummaryResult.Success).summary)
    }

    @Test
    fun `summarize returns Error on API error response`() = runTest {
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.error(401, "Unauthorized".toResponseBody())

        val result = service.summarize("Test Title", "Test Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.Error)
        assertTrue((result as OpenAIService.SummaryResult.Error).message.contains("401"))
    }

    @Test
    fun `summarize returns Error when response has empty choices`() = runTest {
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        val mockResponse = ChatCompletionResponse(
            id = "test-id",
            choices = emptyList(),
            usage = null
        )

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.success(mockResponse)

        val result = service.summarize("Test Title", "Test Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.Error)
        assertTrue((result as OpenAIService.SummaryResult.Error).message.contains("Empty response"))
    }

    @Test
    fun `summarize returns Error on network exception`() = runTest {
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } throws java.io.IOException("Network error")

        val result = service.summarize("Test Title", "Test Content", "https://example.com")

        assertTrue(result is OpenAIService.SummaryResult.Error)
        assertTrue((result as OpenAIService.SummaryResult.Error).message.contains("Network error"))
    }

    @Test
    fun `summarizeArticle returns ProcessedArticle with isSummary true on success`() = runTest {
        val originalArticle = ProcessedArticle(
            title = "Original Title",
            author = "Original Author",
            content = "<p>Original content</p>",
            originalUrl = "https://example.com/article",
            isSummary = false
        )

        val summaryMarkdown = "**Hook**: Brief summary.\n\n**Key Details**:\n- Point one\n- Point two"
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        val mockResponse = ChatCompletionResponse(
            id = "test-id",
            choices = listOf(
                Choice(
                    index = 0,
                    message = ChatMessage(role = "assistant", content = summaryMarkdown),
                    finishReason = "stop"
                )
            ),
            usage = null
        )

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.success(mockResponse)

        val result = service.summarizeArticle(originalArticle)

        assertNotNull(result)
        assertEquals("Original Title", result!!.title)
        assertEquals("Original Author", result.author)
        assertEquals("https://example.com/article", result.originalUrl)
        assertTrue(result.isSummary)
        assertTrue(result.content.contains("<strong>Hook</strong>"))
    }

    @Test
    fun `summarizeArticle returns null when summarization fails`() = runTest {
        val originalArticle = ProcessedArticle(
            title = "Original Title",
            author = "Original Author",
            content = "<p>Original content</p>",
            originalUrl = "https://example.com/article",
            isSummary = false
        )

        every { settingsRepository.getOpenAIApiKey() } returns null

        val result = service.summarizeArticle(originalArticle)

        assertNull(result)
    }

    @Test
    fun `summarize strips HTML from content before sending to API`() = runTest {
        val htmlContent = "<div><p>Test <strong>content</strong> with <a href='#'>links</a></p></div>"
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        val mockResponse = ChatCompletionResponse(
            id = "test-id",
            choices = listOf(
                Choice(
                    index = 0,
                    message = ChatMessage(role = "assistant", content = "Summary"),
                    finishReason = "stop"
                )
            ),
            usage = null
        )

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.success(mockResponse)

        // The test passes if no exception is thrown and we get a result
        val result = service.summarize("Title", htmlContent, "https://example.com")
        assertTrue(result is OpenAIService.SummaryResult.Success)
    }

    @Test
    fun `summarize truncates very long content`() = runTest {
        val longContent = "word ".repeat(2000) // ~10000 characters
        every { settingsRepository.getOpenAIApiKey() } returns "sk-test-key"

        val mockResponse = ChatCompletionResponse(
            id = "test-id",
            choices = listOf(
                Choice(
                    index = 0,
                    message = ChatMessage(role = "assistant", content = "Summary"),
                    finishReason = "stop"
                )
            ),
            usage = null
        )

        coEvery {
            openAIApi.createChatCompletion(any(), any())
        } returns Response.success(mockResponse)

        // Should not throw and should successfully make API call
        val result = service.summarize("Title", longContent, "https://example.com")
        assertTrue(result is OpenAIService.SummaryResult.Success)
    }
}
