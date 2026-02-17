package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

class GhostwriterApiClientTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun sendsAuthHeaderAndNormalizesApiPath() = runTest {
        val engine = MockEngine { request ->
            assertEquals("/api/feeds", request.url.encodedPath)
            assertEquals("Bearer test-key", request.headers[HttpHeaders.Authorization])
            respond(
                content = "[]",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())
            )
        }

        val client = GhostwriterApiClient(
            client = testHttpClient(engine),
            baseUrl = "http://localhost:8159",
            apiKey = "test-key"
        )

        val feeds = client.listFeeds()
        assertEquals(0, feeds.size)
    }

    @Test
    fun omitsAuthHeaderWhenApiKeyMissing() = runTest {
        val engine = MockEngine { request ->
            assertNull(request.headers[HttpHeaders.Authorization])
            respond(
                content = "{\"status\":\"ok\",\"version\":\"1.0\",\"ai_provider\":\"openai\",\"ai_model\":\"gpt-5-nano\"}",
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())
            )
        }

        val client = GhostwriterApiClient(
            client = testHttpClient(engine),
            baseUrl = "http://localhost:8159/api/",
            apiKey = null
        )

        val health = client.getHealth()
        assertEquals("ok", health.status)
    }

    @Test
    fun mapsConflictToTypedException() = runTest {
        val engine = MockEngine {
            respond(
                content = "{\"detail\":\"conflict\"}",
                status = HttpStatusCode.Conflict,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())
            )
        }

        val client = GhostwriterApiClient(
            client = testHttpClient(engine),
            baseUrl = "http://localhost:8159",
            apiKey = "key"
        )

        assertFailsWith<GhostwriterApiException.Conflict> {
            client.getConfig()
        }
    }

    private fun testHttpClient(engine: MockEngine): HttpClient {
        return HttpClient(engine) {
            install(ContentNegotiation) {
                json(json)
            }
        }
    }
}
