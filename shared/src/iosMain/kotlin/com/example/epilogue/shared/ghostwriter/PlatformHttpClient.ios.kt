package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient
import io.ktor.client.engine.darwin.Darwin
import io.ktor.client.plugins.HttpRequestRetry
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

internal actual fun createPlatformHttpClient(): HttpClient {
    return HttpClient(Darwin) {
        install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 15_000
            socketTimeoutMillis = 30_000
        }
        install(HttpRequestRetry) {
            maxRetries = 2
            retryOnServerErrors(maxRetries)
            retryIf { _, response -> response.status.value == 429 }
            exponentialDelay()
        }
        install(ContentNegotiation) {
            json(Json { ignoreUnknownKeys = true })
        }
    }
}
