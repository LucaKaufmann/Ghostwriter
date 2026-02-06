package com.example.epilogue.service

import android.util.Log
import com.example.epilogue.data.remote.openai.ChatCompletionRequest
import com.example.epilogue.data.remote.openai.ChatMessage
import com.example.epilogue.data.remote.openai.OpenAIApi
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.ProcessedArticle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Service for generating article summaries using OpenAI's Chat Completion API.
 * Produces structured summaries with Hook, Key Details, and Significance sections.
 */
@Singleton
class OpenAIService @Inject constructor(
    private val openAIApi: OpenAIApi,
    private val settingsRepository: SettingsRepository
) {

    companion object {
        private const val TAG = "OpenAIService"
        private const val MODEL = "gpt-4o-mini"
        private const val MAX_TOKENS = 512
        private const val TEMPERATURE = 0.7

        /**
         * System prompt enforcing a neutral editor tone suitable for bedtime reading.
         * Produces structured summaries without sensationalism.
         */
        private val SYSTEM_PROMPT = """
            You are a neutral, thoughtful editor preparing a bedtime reading digest. Your goal is to
            summarize articles in a calm, informative tone that helps readers stay informed without
            causing anxiety or overstimulation.

            For each article, provide a structured summary with exactly three sections:

            **Hook**: A single sentence that captures the essence of the story in an engaging but
            non-sensational way.

            **Key Details**: 2-3 bullet points covering the most important facts. Be precise and
            objective. Avoid speculation or editorializing.

            **Significance**: One sentence explaining why this matters or what it means for the
            reader, written in a measured, thoughtful tone.

            Guidelines:
            - Use calm, neutral language throughout
            - Avoid alarming words like "shocking", "breaking", "urgent", "crisis" unless absolutely necessary
            - Present facts without sensationalism
            - Keep the total summary under 150 words
            - Format using Markdown with **bold** headers
            - Do not include the article title in your response

            IMPORTANT - Promotional content handling:
            - Completely ignore any promotional content, deals, discounts, affiliate links, or advertisements
            - Do not mention prices, discount percentages, coupon codes, or special offers
            - If an article is primarily promotional (e.g., "X is Y% off"), respond with only: "PROMOTIONAL_CONTENT"
            - If an article contains some promotional elements mixed with news, focus only on the newsworthy content
            - Never recommend products or services based on price or deals
        """.trimIndent()
    }

    /**
     * Result of a summarization attempt.
     */
    sealed class SummaryResult {
        data class Success(val summary: String) : SummaryResult()
        data class Error(val message: String) : SummaryResult()
        object NoApiKey : SummaryResult()
    }

    /**
     * Summarizes article content using OpenAI.
     *
     * @param title The article title
     * @param content The article content (HTML will be stripped)
     * @param url The original article URL (for context)
     * @return SummaryResult containing the summary or error information
     */
    suspend fun summarize(
        title: String,
        content: String,
        url: String
    ): SummaryResult = withContext(Dispatchers.IO) {
        val apiKey = settingsRepository.getOpenAIApiKey()
        if (apiKey.isNullOrBlank()) {
            return@withContext SummaryResult.NoApiKey
        }

        try {
            val plainText = stripHtml(content)
            val truncatedContent = truncateContent(plainText, maxChars = 4000)

            val userMessage = buildUserMessage(title, truncatedContent, url)

            val request = ChatCompletionRequest(
                model = MODEL,
                messages = listOf(
                    ChatMessage(role = "system", content = SYSTEM_PROMPT),
                    ChatMessage(role = "user", content = userMessage)
                ),
                temperature = TEMPERATURE,
                maxTokens = MAX_TOKENS
            )

            val response = openAIApi.createChatCompletion(
                authorization = "Bearer $apiKey",
                request = request
            )

            if (response.isSuccessful) {
                val body = response.body()
                val summary = body?.choices?.firstOrNull()?.message?.content

                if (summary.isNullOrBlank()) {
                    SummaryResult.Error("Empty response from API")
                } else {
                    SummaryResult.Success(summary.trim())
                }
            } else {
                val errorBody = response.errorBody()?.string()
                SummaryResult.Error("API error: ${response.code()} - $errorBody")
            }
        } catch (e: Exception) {
            SummaryResult.Error("Network error: ${e.message}")
        }
    }

    /**
     * Summarizes an article and returns a ProcessedArticle with isSummary = true.
     *
     * @param originalArticle The original full article
     * @return ProcessedArticle with summary content, or null if summarization fails or content is promotional
     */
    suspend fun summarizeArticle(originalArticle: ProcessedArticle): ProcessedArticle? {
        val result = summarize(
            title = originalArticle.title,
            content = originalArticle.content,
            url = originalArticle.originalUrl
        )

        return when (result) {
            is SummaryResult.Success -> {
                // Filter out articles the AI identified as promotional
                if (result.summary.trim().equals("PROMOTIONAL_CONTENT", ignoreCase = true)) {
                    Log.i(TAG, "AI identified promotional content: ${originalArticle.title}")
                    return null
                }
                ProcessedArticle(
                    title = originalArticle.title,
                    author = originalArticle.author,
                    content = markdownToHtml(result.summary),
                    originalUrl = originalArticle.originalUrl,
                    isSummary = true,
                    feedUrl = originalArticle.feedUrl,
                    feedName = originalArticle.feedName
                )
            }
            else -> null
        }
    }

    /**
     * Builds the user message for the API request.
     */
    private fun buildUserMessage(title: String, content: String, url: String): String {
        return """
            Please summarize the following article:

            Title: $title
            Source: $url

            Content:
            $content
        """.trimIndent()
    }

    /**
     * Strips HTML tags from content.
     */
    private fun stripHtml(html: String): String {
        return html
            .replace(Regex("<[^>]*>"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()
    }

    /**
     * Truncates content to a maximum character count, respecting word boundaries.
     */
    private fun truncateContent(content: String, maxChars: Int): String {
        if (content.length <= maxChars) return content

        val truncated = content.substring(0, maxChars)
        val lastSpace = truncated.lastIndexOf(' ')

        return if (lastSpace > maxChars * 0.8) {
            truncated.substring(0, lastSpace) + "..."
        } else {
            truncated + "..."
        }
    }

    /**
     * Converts basic Markdown to HTML for EPUB compatibility.
     */
    private fun markdownToHtml(markdown: String): String {
        return markdown
            // Bold
            .replace(Regex("\\*\\*(.+?)\\*\\*"), "<strong>$1</strong>")
            // Italic
            .replace(Regex("\\*(.+?)\\*"), "<em>$1</em>")
            // Bullet points
            .replace(Regex("(?m)^- (.+)$"), "<li>$1</li>")
            // Wrap consecutive list items in <ul>
            .replace(Regex("(<li>.*</li>\\n?)+")) { match ->
                "<ul>\n${match.value}</ul>\n"
            }
            // Paragraphs (double newlines)
            .replace(Regex("\\n\\n+"), "</p>\n<p>")
            // Wrap in paragraph tags
            .let { "<p>$it</p>" }
            // Clean up empty paragraphs
            .replace("<p></p>", "")
            .replace(Regex("<p>\\s*</p>"), "")
    }
}
