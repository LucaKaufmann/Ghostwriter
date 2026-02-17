package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpRequestRetry
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import java.io.IOException

internal actual fun createPlatformHttpClient(): HttpClient {
    return HttpClient(OkHttp) {
        install(HttpTimeout) {
            requestTimeoutMillis = 30_000
            connectTimeoutMillis = 15_000
            socketTimeoutMillis = 30_000
        }
        install(HttpRequestRetry) {
            maxRetries = 2
            retryOnServerErrors(maxRetries)
            retryIf { _, response -> response.status.value == 429 }
            retryOnExceptionIf { _, cause -> cause is IOException }
            exponentialDelay()
        }
        install(ContentNegotiation) {
            json(Json { ignoreUnknownKeys = true })
        }
    }
}
