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
        baseUrl = "http://localhost:8159",
        apiKey = null,
        responseBody = """{"status":"ok","version":"1.0","uptime_seconds":1,"last_successful_digest":null,"ai_provider":"openai","ai_model":"gpt-5-nano"}"""
    ) { client, capturedPath, capturedAuth, _, _, _, _ ->
        client.getHealth()
        assertEquals("/api/health", capturedPath())
        assertNull(capturedAuth())
    }

    @Test
    fun deleteFeedByUrl_encodesPathAndSendsAuthHeader() = runClientTest(
        baseUrl = "http://localhost:8159/api",
        apiKey = "abc123",
        responseBody = ""
    ) { client, capturedPath, capturedAuth, _, _, _, _ ->
        client.deleteFeedByUrl("https://example.com/feed")
        assertEquals("/api/feeds/by-url/https://example.com/feed", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
    }

    @Test
    fun downloadDigest_returnsRawBytes() = runClientTest(
        baseUrl = "http://localhost:8159",
        apiKey = "abc123",
        responseBody = "epub-bytes"
    ) { client, capturedPath, capturedAuth, _, _, _, _ ->
        val bytes = client.downloadDigest("digest.epub")
        assertEquals("/api/digests/digest.epub", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
        assertContentEquals("epub-bytes".toByteArray(), bytes)
    }

    @Test
    fun downloadDigestById_usesFormatQueryParameter() = runClientTest(
        baseUrl = "http://localhost:8159",
        apiKey = "abc123",
        responseBody = "pdf-bytes"
    ) { client, capturedPath, capturedAuth, _, _, _, capturedFormat ->
        val bytes = client.downloadDigestById("digest-123", DigestDownloadFormat.PDF)
        assertEquals("/api/digests/digest-123/download", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
        assertEquals("pdf", capturedFormat())
        assertContentEquals("pdf-bytes".toByteArray(), bytes)
    }

    @Test
    fun listDigestsFiltered_includesQueryParameters() = runClientTest(
        baseUrl = "http://localhost:8159",
        apiKey = "abc123",
        responseBody = "[]"
    ) { client, capturedPath, capturedAuth, capturedLimit, capturedOffset, capturedStatus, _ ->
        client.listDigestsFiltered(limit = 50, offset = 10, status = "completed")
        assertEquals("/api/digests", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
        assertEquals("50", capturedLimit())
        assertEquals("10", capturedOffset())
        assertEquals("completed", capturedStatus())
    }

    @Test
    fun listDigests_withoutQueryParameters() = runClientTest(
        baseUrl = "http://localhost:8159",
        apiKey = "abc123",
        responseBody = "[]"
    ) { client, capturedPath, capturedAuth, capturedLimit, capturedOffset, capturedStatus, _ ->
        client.listDigests()
        assertEquals("/api/digests", capturedPath())
        assertEquals("Bearer abc123", capturedAuth())
        assertNull(capturedLimit())
        assertNull(capturedOffset())
        assertNull(capturedStatus())
    }

    private fun runClientTest(
        baseUrl: String,
        apiKey: String?,
        responseBody: String,
        block: suspend (
            client: GhostwriterApiClient,
            capturedPath: () -> String?,
            capturedAuth: () -> String?,
            capturedLimit: () -> String?,
            capturedOffset: () -> String?,
            capturedStatus: () -> String?,
            capturedFormat: () -> String?
        ) -> Unit
    ) {
        var lastPath: String? = null
        var lastAuth: String? = null
        var lastLimit: String? = null
        var lastOffset: String? = null
        var lastStatus: String? = null
        var lastFormat: String? = null

        val engine = MockEngine { request ->
            lastPath = request.url.encodedPath
            lastAuth = request.headers[HttpHeaders.Authorization]
            lastLimit = request.url.parameters["limit"]
            lastOffset = request.url.parameters["offset"]
            lastStatus = request.url.parameters["status"]
            lastFormat = request.url.parameters["format"]
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
                { lastAuth },
                { lastLimit },
                { lastOffset },
                { lastStatus },
                { lastFormat }
            )
        }
        httpClient.close()
    }
}
