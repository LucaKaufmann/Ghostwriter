package com.example.epilogue.data.remote.ghostwriter

import com.example.epilogue.shared.ghostwriter.GhostwriterApiClient
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class SharedGhostwriterAdapterTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun performSync_mapsResponseToAppModels() = runTest {
        val payload = """
            {
              "config": {
                "min_word_count": 200,
                "morning_hour": 7,
                "morning_minute": 0,
                "noon_hour": 12,
                "noon_minute": 0,
                "evening_hour": 18,
                "evening_minute": 0,
                "timezone": "UTC",
                "updated_at": "2026-02-17T10:00:00"
              },
              "feeds": { "feeds": [], "tombstones": [], "server_timestamp": "2026-02-17T10:00:01" },
              "digests": { "new_digests": [] },
              "schedules": []
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.performSync(feedSince = null, digestIds = null)

        assertEquals("UTC", result.config.timezone)
        assertEquals(200, result.config.minWordCount)
        adapter.close()
    }

    @Test
    fun getFeedChanges_mapsFeedsAndTombstones() = runTest {
        val payload = """
            {
              "feeds": [
                {
                  "id": "f1",
                  "url": "https://example.com/feed",
                  "title": "Example",
                  "is_active": true,
                  "mode": "raw",
                  "max_articles": 10,
                  "created_at": "2026-02-17T10:00:00",
                  "updated_at": "2026-02-17T10:05:00"
                }
              ],
              "tombstones": [
                { "url": "https://example.com/deleted", "deleted_at": "2026-02-17T10:06:00" }
              ],
              "server_timestamp": "2026-02-17T10:07:00"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getFeedChanges(since = null)

        assertEquals(1, result.feeds.size)
        assertEquals("Example", result.feeds.first().title)
        assertEquals(1, result.tombstones.size)
        assertEquals("2026-02-17T10:07:00", result.serverTimestamp)
        adapter.close()
    }

    @Test
    fun listDigests_mapsDigestList() = runTest {
        val payload = """
            [
              {
                "id": "d1",
                "filename": "file.epub",
                "period": "manual",
                "status": "completed",
                "stage": null,
                "article_count": 3,
                "error_message": null,
                "created_at": "2026-02-17T10:00:00",
                "completed_at": "2026-02-17T10:10:00"
              }
            ]
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.listDigests()

        assertEquals(1, result.size)
        assertEquals("d1", result.first().id)
        assertEquals(3, result.first().articleCount)
        adapter.close()
    }

    @Test
    fun updateConfig_mapsResponseToAppModel() = runTest {
        val payload = """
            {
              "min_word_count": 150,
              "morning_hour": 6,
              "morning_minute": 30,
              "noon_hour": 12,
              "noon_minute": 0,
              "evening_hour": 18,
              "evening_minute": 0,
              "timezone": "America/New_York",
              "updated_at": "2026-02-17T12:00:00"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.updateConfig(
            ClientConfigUpdateRequest(minWordCount = 150)
        )

        assertEquals(150, result.minWordCount)
        assertEquals("America/New_York", result.timezone)
        adapter.close()
    }

    private fun adapterWithJson(payload: String): SharedGhostwriterAdapter {
        val engine = MockEngine {
            respond(
                content = payload,
                status = HttpStatusCode.OK,
                headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())
            )
        }
        val httpClient = HttpClient(engine) {
            install(ContentNegotiation) { json(json) }
        }
        val shared = GhostwriterApiClient(httpClient, "http://localhost:8159", "key")
        return SharedGhostwriterAdapter.fromClient(httpClient, shared)
    }
}
