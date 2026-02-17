package com.example.epilogue.shared.ghostwriter

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class FeedSyncRequest(
    @SerialName("url") val url: String,
    @SerialName("title") val title: String,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("mode") val mode: String = "raw",
    @SerialName("max_articles") val maxArticles: Int = 10
)

@Serializable
data class FeedSyncResponse(
    @SerialName("synced") val synced: Int,
    @SerialName("created") val created: Int,
    @SerialName("updated") val updated: Int,
    @SerialName("unchanged") val unchanged: Int
)

@Serializable
data class FeedResponse(
    @SerialName("id") val id: String,
    @SerialName("url") val url: String,
    @SerialName("title") val title: String,
    @SerialName("is_active") val isActive: Boolean,
    @SerialName("mode") val mode: String,
    @SerialName("max_articles") val maxArticles: Int,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
    @SerialName("deleted_at") val deletedAt: String? = null
)

@Serializable
data class FeedTombstoneResponse(
    @SerialName("url") val url: String,
    @SerialName("deleted_at") val deletedAt: String
)

@Serializable
data class FeedChangesResponse(
    @SerialName("feeds") val feeds: List<FeedResponse>,
    @SerialName("tombstones") val tombstones: List<FeedTombstoneResponse>,
    @SerialName("server_timestamp") val serverTimestamp: String
)

@Serializable
data class DigestTriggerRequest(
    @SerialName("period") val period: String = "manual"
)

@Serializable
data class DigestTriggerResponse(
    @SerialName("id") val id: String? = null,
    @SerialName("status") val status: String,
    @SerialName("message") val message: String
)

@Serializable
data class DigestProgress(
    @SerialName("total_feeds") val totalFeeds: Int,
    @SerialName("feeds_fetched") val feedsFetched: Int,
    @SerialName("total_articles") val totalArticles: Int,
    @SerialName("articles_enriched") val articlesEnriched: Int
)

@Serializable
data class DigestStatusResponse(
    @SerialName("id") val id: String,
    @SerialName("status") val status: String,
    @SerialName("stage") val stage: String? = null,
    @SerialName("progress") val progress: DigestProgress,
    @SerialName("started_at") val startedAt: String,
    @SerialName("eta_seconds") val etaSeconds: Int? = null
)

@Serializable
data class DigestResponse(
    @SerialName("id") val id: String,
    @SerialName("filename") val filename: String,
    @SerialName("period") val period: String,
    @SerialName("status") val status: String,
    @SerialName("stage") val stage: String? = null,
    @SerialName("article_count") val articleCount: Int,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("completed_at") val completedAt: String? = null
)

@Serializable
data class DigestArticleResponse(
    @SerialName("id") val id: String,
    @SerialName("title") val title: String,
    @SerialName("url") val url: String,
    @SerialName("mode") val mode: String,
    @SerialName("word_count") val wordCount: Int,
    @SerialName("content") val content: String,
    @SerialName("author") val author: String? = null,
    @SerialName("feed_title") val feedTitle: String,
    @SerialName("sort_order") val sortOrder: Int,
    @SerialName("ai_failed") val aiFailed: Boolean = false
)

@Serializable
data class DigestArticlesResponse(
    @SerialName("digest_id") val digestId: String,
    @SerialName("article_count") val articleCount: Int,
    @SerialName("articles") val articles: List<DigestArticleResponse>
)

@Serializable
data class DigestArticleSourceResponse(
    @SerialName("digest_id") val digestId: String,
    @SerialName("article_id") val articleId: String,
    @SerialName("url") val url: String,
    @SerialName("final_url") val finalUrl: String,
    @SerialName("content_type") val contentType: String? = null,
    @SerialName("fetched_at") val fetchedAt: String,
    @SerialName("size_bytes") val sizeBytes: Long,
    @SerialName("html") val html: String
)

@Serializable
data class ScheduleResponse(
    @SerialName("id") val id: String,
    @SerialName("period") val period: String,
    @SerialName("hour") val hour: Int,
    @SerialName("minute") val minute: Int,
    @SerialName("enabled") val enabled: Boolean,
    @SerialName("timezone") val timezone: String,
    @SerialName("next_run_at") val nextRunAt: String? = null
)

@Serializable
data class ScheduleUpdateRequest(
    @SerialName("hour") val hour: Int? = null,
    @SerialName("minute") val minute: Int? = null,
    @SerialName("enabled") val enabled: Boolean? = null,
    @SerialName("timezone") val timezone: String? = null
)

@Serializable
data class ClientStatusResponse(
    @SerialName("last_heartbeat_at") val lastHeartbeatAt: String? = null,
    @SerialName("last_download_at") val lastDownloadAt: String? = null,
    @SerialName("last_feed_sync_at") val lastFeedSyncAt: String? = null,
    @SerialName("auto_disable_enabled") val autoDisableEnabled: Boolean,
    @SerialName("auto_disable_after_days") val autoDisableAfterDays: Int,
    @SerialName("schedules_auto_disabled") val schedulesAutoDisabled: Boolean,
    @SerialName("auto_disabled_at") val autoDisabledAt: String? = null,
    @SerialName("days_until_auto_disable") val daysUntilAutoDisable: Int? = null
)

@Serializable
data class HeartbeatResponse(
    @SerialName("status") val status: String,
    @SerialName("received_at") val receivedAt: String,
    @SerialName("schedules_active") val schedulesActive: Boolean,
    @SerialName("message") val message: String? = null
)

@Serializable
data class IntegrationStatus(
    @SerialName("enabled") val enabled: Boolean,
    @SerialName("label") val label: String? = null
)

@Serializable
data class ClientConfigResponse(
    @SerialName("min_word_count") val minWordCount: Int? = null,
    @SerialName("morning_hour") val morningHour: Int? = null,
    @SerialName("morning_minute") val morningMinute: Int? = null,
    @SerialName("noon_hour") val noonHour: Int? = null,
    @SerialName("noon_minute") val noonMinute: Int? = null,
    @SerialName("evening_hour") val eveningHour: Int? = null,
    @SerialName("evening_minute") val eveningMinute: Int? = null,
    @SerialName("timezone") val timezone: String,
    @SerialName("schedule_morning") val scheduleMorning: String? = null,
    @SerialName("schedule_noon") val scheduleNoon: String? = null,
    @SerialName("schedule_evening") val scheduleEvening: String? = null,
    @SerialName("whisper_provider") val whisperProvider: String? = null,
    @SerialName("whisper_model") val whisperModel: String? = null,
    @SerialName("whisper_timeout_minutes") val whisperTimeoutMinutes: Int? = null,
    @SerialName("media_processing_interval_hours") val mediaProcessingIntervalHours: Int? = null,
    @SerialName("include_podcasts_in_digest") val includePodcastsInDigest: Boolean? = null,
    @SerialName("include_youtube_in_digest") val includeYoutubeInDigest: Boolean? = null,
    @SerialName("cover_enabled") val coverEnabled: Boolean? = null,
    @SerialName("cover_provider") val coverProvider: String? = null,
    @SerialName("cover_quality") val coverQuality: String? = null,
    @SerialName("cover_prompt") val coverPrompt: String? = null,
    @SerialName("cover_overlay_enabled") val coverOverlayEnabled: Boolean? = null,
    @SerialName("cover_openai_api_key") val coverOpenAiApiKey: String? = null,
    @SerialName("cover_gemini_api_key") val coverGeminiApiKey: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("wallabag") val wallabag: IntegrationStatus? = null,
    @SerialName("newsletters") val newsletters: IntegrationStatus? = null
)

@Serializable
data class ClientConfigUpdateRequest(
    @SerialName("min_word_count") val minWordCount: Int? = null,
    @SerialName("morning_hour") val morningHour: Int? = null,
    @SerialName("morning_minute") val morningMinute: Int? = null,
    @SerialName("noon_hour") val noonHour: Int? = null,
    @SerialName("noon_minute") val noonMinute: Int? = null,
    @SerialName("evening_hour") val eveningHour: Int? = null,
    @SerialName("evening_minute") val eveningMinute: Int? = null,
    @SerialName("timezone") val timezone: String? = null,
    @SerialName("schedule_morning") val scheduleMorning: String? = null,
    @SerialName("schedule_noon") val scheduleNoon: String? = null,
    @SerialName("schedule_evening") val scheduleEvening: String? = null,
    @SerialName("include_podcasts_in_digest") val includePodcastsInDigest: Boolean? = null,
    @SerialName("include_youtube_in_digest") val includeYoutubeInDigest: Boolean? = null,
    @SerialName("cover_enabled") val coverEnabled: Boolean? = null,
    @SerialName("cover_provider") val coverProvider: String? = null,
    @SerialName("cover_quality") val coverQuality: String? = null,
    @SerialName("cover_prompt") val coverPrompt: String? = null,
    @SerialName("cover_overlay_enabled") val coverOverlayEnabled: Boolean? = null,
    @SerialName("client_updated_at") val clientUpdatedAt: String? = null
)

@Serializable
data class SyncResponse(
    @SerialName("config") val config: ClientConfigResponse,
    @SerialName("feeds") val feeds: FeedChangesResponse,
    @SerialName("digests") val digests: SyncDigestsSection,
    @SerialName("schedules") val schedules: List<ScheduleResponse>
)

@Serializable
data class SyncDigestsSection(
    @SerialName("new_digests") val newDigests: List<SyncDigest>
)

@Serializable
data class SyncDigest(
    @SerialName("id") val id: String,
    @SerialName("filename") val filename: String,
    @SerialName("period") val period: String,
    @SerialName("status") val status: String,
    @SerialName("stage") val stage: String? = null,
    @SerialName("article_count") val articleCount: Int,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("completed_at") val completedAt: String? = null,
    @SerialName("articles") val articles: List<DigestArticleResponse>
)
