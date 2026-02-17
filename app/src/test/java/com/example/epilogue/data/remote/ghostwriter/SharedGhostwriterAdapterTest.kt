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

    @Test
    fun getConfig_mapsResponseToAppModel() = runTest {
        val payload = """
            {
              "min_word_count": 99,
              "morning_hour": 7,
              "morning_minute": 0,
              "noon_hour": 12,
              "noon_minute": 0,
              "evening_hour": 18,
              "evening_minute": 0,
              "timezone": "UTC",
              "updated_at": "2026-02-17T12:30:00"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getConfig()

        assertEquals(99, result.minWordCount)
        assertEquals("UTC", result.timezone)
        adapter.close()
    }

    @Test
    fun getClientStatus_mapsResponseToAppModel() = runTest {
        val payload = """
            {
              "last_heartbeat_at": "2026-02-17T11:00:00",
              "last_download_at": "2026-02-17T10:00:00",
              "auto_disable_enabled": true,
              "auto_disable_after_days": 7,
              "schedules_auto_disabled": false,
              "days_until_auto_disable": 5
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getClientStatus()

        assertEquals(true, result.autoDisableEnabled)
        assertEquals(7, result.autoDisableAfterDays)
        assertEquals(false, result.schedulesAutoDisabled)
        assertEquals(5, result.daysUntilAutoDisable)
        adapter.close()
    }

    @Test
    fun sendHeartbeat_mapsResponseToAppModel() = runTest {
        val payload = """
            {
              "status": "ok",
              "received_at": "2026-02-17T11:00:00",
              "schedules_active": true,
              "message": "received"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.sendHeartbeat()

        assertEquals("ok", result.status)
        assertEquals(true, result.schedulesActive)
        assertEquals("received", result.message)
        adapter.close()
    }

    @Test
    fun getSchedules_mapsResponseList() = runTest {
        val payload = """
            [
              {
                "id": "s1",
                "period": "morning",
                "hour": 7,
                "minute": 0,
                "enabled": true,
                "timezone": "UTC",
                "next_run_at": "2026-02-18T07:00:00"
              }
            ]
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getSchedules()

        assertEquals(1, result.size)
        assertEquals("morning", result.first().period)
        assertEquals(true, result.first().enabled)
        adapter.close()
    }

    @Test
    fun updateSchedule_mapsResponseModel() = runTest {
        val payload = """
            {
              "id": "s1",
              "period": "morning",
              "hour": 8,
              "minute": 15,
              "enabled": false,
              "timezone": "UTC",
              "next_run_at": null
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.updateSchedule(
            period = "morning",
            request = ScheduleUpdateRequest(enabled = false, hour = 8, minute = 15)
        )

        assertEquals("morning", result.period)
        assertEquals(8, result.hour)
        assertEquals(15, result.minute)
        assertEquals(false, result.enabled)
        adapter.close()
    }

    @Test
    fun previewWallabag_mapsPreviewPayload() = runTest {
        val payload = """
            {
              "status": "ok",
              "count": 1,
              "articles": [
                {
                  "title": "Sample",
                  "url": "https://example.com/a",
                  "author": "Author",
                  "word_count": 123
                }
              ],
              "detail": null
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.previewWallabag()

        assertEquals("ok", result.status)
        assertEquals(1, result.count)
        assertEquals(1, result.articles.size)
        assertEquals(123, result.articles.first().wordCount)
        adapter.close()
    }

    @Test
    fun previewNewsletters_mapsPreviewPayload() = runTest {
        val payload = """
            {
              "status": "ok",
              "count": 0,
              "articles": [],
              "detail": "none"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.previewNewsletters()

        assertEquals("ok", result.status)
        assertEquals(0, result.count)
        assertEquals("none", result.detail)
        adapter.close()
    }

    @Test
    fun clearWallabagSeen_mapsResponse() = runTest {
        val payload = """{"cleared": 4}"""
        val adapter = adapterWithJson(payload)
        val result = adapter.clearWallabagSeen()
        assertEquals(4, result.cleared)
        adapter.close()
    }

    @Test
    fun clearNewsletterSeen_mapsResponse() = runTest {
        val payload = """{"cleared": 2}"""
        val adapter = adapterWithJson(payload)
        val result = adapter.clearNewsletterSeen()
        assertEquals(2, result.cleared)
        adapter.close()
    }

    @Test
    fun getLogFiles_mapsResponse() = runTest {
        val payload = """
            [
              {
                "filename": "ghostwriter.log",
                "size_bytes": 1024,
                "modified_at": "2026-02-17T12:00:00"
              }
            ]
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getLogFiles()
        assertEquals(1, result.size)
        assertEquals("ghostwriter.log", result.first().filename)
        assertEquals(1024L, result.first().sizeBytes)
        adapter.close()
    }

    @Test
    fun listAuthTokens_mapsResponse() = runTest {
        val payload = """
            [
              {
                "id": "t1",
                "name": "CLI",
                "token_prefix": "gw_abc",
                "created_at": "2026-02-17T12:00:00",
                "last_used_at": null,
                "revoked_at": null
              }
            ]
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.listAuthTokens()
        assertEquals(1, result.size)
        assertEquals("t1", result.first().id)
        assertEquals("gw_abc", result.first().tokenPrefix)
        adapter.close()
    }

    @Test
    fun createAuthToken_mapsResponse() = runTest {
        val payload = """
            {
              "id": "t2",
              "name": "Mobile",
              "token": "gw_secret",
              "token_prefix": "gw_sec",
              "created_at": "2026-02-17T12:05:00"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.createAuthToken("Mobile")
        assertEquals("t2", result.id)
        assertEquals("gw_secret", result.token)
        adapter.close()
    }

    @Test
    fun revokeAuthToken_mapsResponse() = runTest {
        val payload = """{"status":"ok","message":"revoked"}"""
        val adapter = adapterWithJson(payload)
        val result = adapter.revokeAuthToken("t1")
        assertEquals("ok", result.status)
        assertEquals("revoked", result.message)
        adapter.close()
    }

    @Test
    fun getMediaStatus_mapsResponse() = runTest {
        val payload = """
            {
              "is_running": true,
              "pending_count": 4,
              "processing_count": 1,
              "completed_count": 20,
              "failed_count": 0,
              "current_item_title": "Episode 1",
              "current_item_content_type": "podcast",
              "last_completed_at": "2026-02-17T13:00:00",
              "next_run_at": "2026-02-17T14:00:00"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getMediaStatus()
        assertEquals(true, result.isRunning)
        assertEquals(4, result.pendingCount)
        assertEquals("Episode 1", result.currentItemTitle)
        adapter.close()
    }

    @Test
    fun triggerMediaProcessing_mapsResponse() = runTest {
        val payload = """{"status":"queued","detail":"started"}"""
        val adapter = adapterWithJson(payload)
        val result = adapter.triggerMediaProcessing()
        assertEquals("queued", result.status)
        assertEquals("started", result.detail)
        adapter.close()
    }

    @Test
    fun getPodcastFeeds_mapsResponse() = runTest {
        val payload = """
            [
              {
                "id": "m1",
                "feed_type": "podcast",
                "url": "https://example.com/podcast.rss",
                "resolved_feed_url": null,
                "title": "Podcast",
                "is_active": true,
                "mode": "raw",
                "max_items": 5,
                "created_at": "2026-02-17T12:00:00",
                "updated_at": "2026-02-17T12:30:00",
                "deleted_at": null
              }
            ]
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.getPodcastFeeds()
        assertEquals(1, result.size)
        assertEquals("podcast", result.first().feedType)
        adapter.close()
    }

    @Test
    fun createPodcastFeed_mapsResponse() = runTest {
        val payload = """
            {
              "id": "m1",
              "feed_type": "podcast",
              "url": "https://example.com/podcast.rss",
              "resolved_feed_url": null,
              "title": "Podcast",
              "is_active": true,
              "mode": "raw",
              "max_items": 5,
              "created_at": "2026-02-17T12:00:00",
              "updated_at": "2026-02-17T12:30:00",
              "deleted_at": null
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.createPodcastFeed(
            MediaFeedCreateRequest(feedType = "podcast", url = "https://example.com/podcast.rss", title = "Podcast")
        )
        assertEquals("m1", result.id)
        assertEquals("Podcast", result.title)
        adapter.close()
    }

    @Test
    fun resolveYouTubeFeed_mapsResponse() = runTest {
        val payload = """
            {
              "rss_feed_url": "https://www.youtube.com/feeds/videos.xml?channel_id=abc",
              "channel_id": "abc",
              "channel_title": "Channel"
            }
        """.trimIndent()

        val adapter = adapterWithJson(payload)
        val result = adapter.resolveYouTubeFeed("https://youtube.com/@channel")
        assertEquals("abc", result.channelId)
        assertEquals("Channel", result.channelTitle)
        adapter.close()
    }

    @Test
    fun deleteYouTubeFeed_mapsStatusResponse() = runTest {
        val payload = """{"status":"ok","message":"deleted"}"""
        val adapter = adapterWithJson(payload)
        val result = adapter.deleteYouTubeFeed("m2")
        assertEquals("ok", result.status)
        assertEquals("deleted", result.message)
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
