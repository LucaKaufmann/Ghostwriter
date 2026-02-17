package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient

/**
 * Owns a platform HttpClient + GhostwriterApiClient pair so Apple/Android callers
 * can construct and dispose shared networking cleanly from platform code.
 */
class GhostwriterClientHandle private constructor(
    private val httpClient: HttpClient,
    val client: GhostwriterApiClient
) {
    fun close() {
        httpClient.close()
    }

    companion object {
        fun create(baseUrl: String, apiKey: String?): GhostwriterClientHandle {
            val httpClient = createPlatformHttpClient()
            val client = GhostwriterApiClient(
                client = httpClient,
                baseUrl = baseUrl,
                apiKey = apiKey
            )
            return GhostwriterClientHandle(
                httpClient = httpClient,
                client = client
            )
        }
    }
}
