package com.example.epilog.data.remote.openai

import com.google.gson.annotations.SerializedName

/**
 * OpenAI Chat Completion API request/response models.
 * https://platform.openai.com/docs/api-reference/chat/create
 */

data class ChatCompletionRequest(
    val model: String = "gpt-4o-mini",
    val messages: List<ChatMessage>,
    val temperature: Double = 0.7,
    @SerializedName("max_tokens")
    val maxTokens: Int = 1024
)

data class ChatMessage(
    val role: String,  // "system", "user", "assistant"
    val content: String
)

data class ChatCompletionResponse(
    val id: String,
    val choices: List<Choice>,
    val usage: Usage?
)

data class Choice(
    val index: Int,
    val message: ChatMessage,
    @SerializedName("finish_reason")
    val finishReason: String?
)

data class Usage(
    @SerializedName("prompt_tokens")
    val promptTokens: Int,
    @SerializedName("completion_tokens")
    val completionTokens: Int,
    @SerializedName("total_tokens")
    val totalTokens: Int
)

data class OpenAIError(
    val error: ErrorDetails?
)

data class ErrorDetails(
    val message: String?,
    val type: String?,
    val code: String?
)
