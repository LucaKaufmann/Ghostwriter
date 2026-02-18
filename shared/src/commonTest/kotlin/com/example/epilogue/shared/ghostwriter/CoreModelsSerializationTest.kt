package com.example.epilogue.shared.ghostwriter

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CoreModelsSerializationTest {
    private val json = Json {
        ignoreUnknownKeys = true
    }

    @Test
    fun decodesFeedChangesPayload() {
        val payload = """
            {
              "feeds": [
                {
                  "id": "feed-1",
                  "url": "https://example.com/feed",
                  "title": "Example Feed",
                  "is_active": true,
                  "mode": "raw",
                  "max_articles": 10,
                  "created_at": "2026-02-17T10:00:00",
                  "updated_at": "2026-02-17T10:30:00"
                }
              ],
              "tombstones": [
                {
                  "url": "https://example.com/deleted",
                  "deleted_at": "2026-02-17T11:00:00"
                }
              ],
              "server_timestamp": "2026-02-17T11:30:00"
            }
        """.trimIndent()

        val response = json.decodeFromString<FeedChangesResponse>(payload)

        assertEquals(1, response.feeds.size)
        assertEquals("Example Feed", response.feeds.first().title)
        assertEquals(1, response.tombstones.size)
        assertEquals("2026-02-17T11:30:00", response.serverTimestamp)
    }

    @Test
    fun decodesCombinedSyncPayload() {
        val payload = """
            {
              "config": {
                "min_word_count": 300,
                "morning_hour": 7,
                "morning_minute": 0,
                "noon_hour": 12,
                "noon_minute": 0,
                "evening_hour": 18,
                "evening_minute": 0,
                "timezone": "America/New_York",
                "updated_at": "2026-02-17T12:00:00"
              },
              "feeds": {
                "feeds": [],
                "tombstones": [],
                "server_timestamp": "2026-02-17T12:01:00"
              },
              "digests": {
                "new_digests": [
                  {
                    "id": "digest-1",
                    "filename": "2026-02-17_morning.epub",
                    "period": "morning",
                    "status": "completed",
                    "stage": null,
                    "article_count": 1,
                    "error_message": null,
                    "created_at": "2026-02-17T12:00:00",
                    "completed_at": "2026-02-17T12:05:00",
                    "articles": [
                      {
                        "id": "article-1",
                        "title": "Hello",
                        "url": "https://example.com/article",
                        "mode": "raw",
                        "word_count": 800,
                        "content": "<p>content</p>",
                        "author": null,
                        "feed_title": "Example Feed",
                        "sort_order": 0,
                        "ai_failed": false
                      }
                    ]
                  }
                ]
              },
              "schedules": [
                {
                  "id": "morning",
                  "period": "morning",
                  "hour": 7,
                  "minute": 0,
                  "enabled": true,
                  "timezone": "America/New_York",
                  "next_run_at": "2026-02-18T07:00:00"
                }
              ]
            }
        """.trimIndent()

        val response = json.decodeFromString<SyncResponse>(payload)

        assertEquals("America/New_York", response.config.timezone)
        assertEquals(1, response.digests.newDigests.size)
        assertEquals(1, response.digests.newDigests.first().articles.size)
        assertTrue(response.schedules.first().enabled)
    }

    @Test
    fun encodesClientConfigUpdateUsingWireKeys() {
        val request = ClientConfigUpdateRequest(
            minWordCount = 150,
            morningHour = 6,
            morningMinute = 30,
            timezone = "America/Los_Angeles",
            clientUpdatedAt = "2026-02-17T13:00:00"
        )

        val encoded = json.encodeToString(ClientConfigUpdateRequest.serializer(), request)

        assertTrue(encoded.contains("\"min_word_count\":150"))
        assertTrue(encoded.contains("\"morning_hour\":6"))
        assertTrue(encoded.contains("\"morning_minute\":30"))
        assertTrue(encoded.contains("\"client_updated_at\":\"2026-02-17T13:00:00\""))
    }
}
