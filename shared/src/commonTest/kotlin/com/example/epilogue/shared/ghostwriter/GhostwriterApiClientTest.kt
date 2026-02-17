package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlinx.serialization.json.Json

class GhostwriterApiClientTest {

    @Test
    fun getHealth_usesApiPrefixedBaseUrlWithoutAuthHeader() = runClientTest(
        baseUrl = "http://localhost:8080",
        apiKey = null,
        responseBody = """{"status":"ok","version":"1.0","uptime_seconds":1,"last_successful_digest":null,"ai_provider":"openai","ai_model":"gpt-5-nano"}"""
    ) { client, capturedPath, capturedAuth ->
        client.getHealth()
        assertEquals("/api/health", capturedPath())
        assertNull(capturedAuth())
    }

    @Test
    fun deleteFeedByUrl_encodesPathAndSendsAuthHeader() = runClientTest(
        baseUrl = "http://localhost:8080/api",
        apiKey = "abc123",
        responseBody = ""
    ) { client, capturedPath, capturedAuth ->
        client.deleteFeedByUrl("https://example.com/feed")
        assertEquals("/api/feeds/by-url/https://example.com/feed", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
    }

    @Test
    fun downloadDigest_returnsRawBytes() = runClientTest(
        baseUrl = "http://localhost:8080",
        apiKey = "abc123",
        responseBody = "epub-bytes"
    ) { client, capturedPath, capturedAuth ->
        val bytes = client.downloadDigest("digest.epub")
        assertEquals("/api/digests/digest.epub", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
        assertContentEquals("epub-bytes".toByteArray(), bytes)
    }

    private fun runClientTest(
        baseUrl: String,
        apiKey: String?,
        responseBody: String,
        block: suspend (
            client: GhostwriterApiClient,
            capturedPath: () -> String?,
            capturedAuth: () -> String?
        ) -> Unit
    ) {
        var lastPath: String? = null
        var lastAuth: String? = null

        val engine = MockEngine { request ->
            lastPath = request.url.encodedPath
            lastAuth = request.headers[HttpHeaders.Authorization]
            respond(
                content = responseBody,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, "application/json")
            )
        }

        val httpClient = HttpClient(engine) {
            install(ContentNegotiation) {
                json(Json { ignoreUnknownKeys = true })
            }
        }
        val client = GhostwriterApiClient(httpClient, baseUrl, apiKey)
        kotlinx.coroutines.test.runTest {
            block(
                client,
                { lastPath },
                { lastAuth }
            )
        }
        httpClient.close()
    }
}
