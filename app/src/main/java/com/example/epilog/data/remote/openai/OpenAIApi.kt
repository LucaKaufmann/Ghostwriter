package com.example.epilog.data.remote.openai

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.Header
import retrofit2.http.POST

/**
 * Retrofit interface for OpenAI Chat Completion API.
 */
interface OpenAIApi {

    @POST("v1/chat/completions")
    suspend fun createChatCompletion(
        @Header("Authorization") authorization: String,
        @Body request: ChatCompletionRequest
    ): Response<ChatCompletionResponse>

    companion object {
        const val BASE_URL = "https://api.openai.com/"
    }
}
