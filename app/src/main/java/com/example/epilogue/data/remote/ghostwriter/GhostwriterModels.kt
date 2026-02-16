package com.example.epilogue.data.remote.ghostwriter

import com.google.gson.annotations.SerializedName

/**
 * Feed sync request model - matches Ghostwriter's FeedSync schema.
 */
data class FeedSyncRequest(
    @SerializedName("url") val url: String,
    @SerializedName("title") val title: String,
    @SerializedName("is_active") val isActive: Boolean = true,
    @SerializedName("mode") val mode: String = "raw", // "raw" or "summarize"
    @SerializedName("max_articles") val maxArticles: Int = 10
)

/**
 * Feed sync response model.
 */
data class FeedSyncResponse(
    @SerializedName("synced") val synced: Int,
    @SerializedName("created") val created: Int,
    @SerializedName("updated") val updated: Int,
    @SerializedName("unchanged") val unchanged: Int
)

/**
 * Feed response model from Ghostwriter.
 */
data class FeedResponse(
    @SerializedName("id") val id: String,
    @SerializedName("url") val url: String,
    @SerializedName("title") val title: String,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("mode") val mode: String,
    @SerializedName("max_articles") val maxArticles: Int,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

/**
 * Digest trigger request model.
 */
data class DigestTriggerRequest(
    @SerializedName("period") val period: String = "manual" // morning, noon, evening, manual
)

/**
 * Digest trigger response model.
 */
data class DigestTriggerResponse(
    @SerializedName("id") val id: String?,
    @SerializedName("status") val status: String,
    @SerializedName("message") val message: String
)

/**
 * Digest progress information.
 */
data class DigestProgress(
    @SerializedName("total_feeds") val totalFeeds: Int,
    @SerializedName("feeds_fetched") val feedsFetched: Int,
    @SerializedName("total_articles") val totalArticles: Int,
    @SerializedName("articles_enriched") val articlesEnriched: Int
)

/**
 * Digest status response for polling.
 */
data class DigestStatusResponse(
    @SerializedName("id") val id: String,
    @SerializedName("status") val status: String, // queued, processing, completed, failed
    @SerializedName("stage") val stage: String?, // fetching, extracting, enriching, compiling
    @SerializedName("progress") val progress: DigestProgress,
    @SerializedName("started_at") val startedAt: String,
    @SerializedName("eta_seconds") val etaSeconds: Int?
)

/**
 * Digest list item response.
 */
data class DigestResponse(
    @SerializedName("id") val id: String,
    @SerializedName("filename") val filename: String,
    @SerializedName("period") val period: String,
    @SerializedName("status") val status: String,
    @SerializedName("stage") val stage: String?,
    @SerializedName("article_count") val articleCount: Int,
    @SerializedName("error_message") val errorMessage: String?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("completed_at") val completedAt: String?
)

/**
 * Health check response.
 */
data class HealthResponse(
    @SerializedName("status") val status: String,
    @SerializedName("version") val version: String,
    @SerializedName("uptime_seconds") val uptimeSeconds: Int?,
    @SerializedName("last_successful_digest") val lastSuccessfulDigest: String?,
    @SerializedName("ai_provider") val aiProvider: String,
    @SerializedName("ai_model") val aiModel: String
)

/**
 * Schedule response from Ghostwriter.
 */
data class ScheduleResponse(
    @SerializedName("id") val id: String,
    @SerializedName("period") val period: String,
    @SerializedName("hour") val hour: Int,
    @SerializedName("minute") val minute: Int,
    @SerializedName("enabled") val enabled: Boolean,
    @SerializedName("timezone") val timezone: String,
    @SerializedName("next_run_at") val nextRunAt: String?
)

/**
 * Schedule update request.
 */
data class ScheduleUpdateRequest(
    @SerializedName("hour") val hour: Int? = null,
    @SerializedName("minute") val minute: Int? = null,
    @SerializedName("enabled") val enabled: Boolean? = null,
    @SerializedName("timezone") val timezone: String? = null
)

/**
 * Client status response.
 */
data class ClientStatusResponse(
    @SerializedName("last_heartbeat_at") val lastHeartbeatAt: String?,
    @SerializedName("last_download_at") val lastDownloadAt: String?,
    @SerializedName("auto_disable_enabled") val autoDisableEnabled: Boolean,
    @SerializedName("auto_disable_after_days") val autoDisableAfterDays: Int,
    @SerializedName("schedules_auto_disabled") val schedulesAutoDisabled: Boolean,
    @SerializedName("days_until_auto_disable") val daysUntilAutoDisable: Int?
)

/**
 * Heartbeat response.
 */
data class HeartbeatResponse(
    @SerializedName("status") val status: String,
    @SerializedName("received_at") val receivedAt: String,
    @SerializedName("schedules_active") val schedulesActive: Boolean,
    @SerializedName("message") val message: String?
)

/**
 * Digest article with content - for syncing article content to the app.
 */
data class DigestArticleResponse(
    @SerializedName("id") val id: String,
    @SerializedName("title") val title: String,
    @SerializedName("url") val url: String,
    @SerializedName("mode") val mode: String,
    @SerializedName("word_count") val wordCount: Int,
    @SerializedName("content") val content: String,
    @SerializedName("author") val author: String?,
    @SerializedName("feed_title") val feedTitle: String,
    @SerializedName("sort_order") val sortOrder: Int,
    @SerializedName("ai_failed") val aiFailed: Boolean
)

/**
 * Response containing all articles for a digest.
 */
data class DigestArticlesResponse(
    @SerializedName("digest_id") val digestId: String,
    @SerializedName("article_count") val articleCount: Int,
    @SerializedName("articles") val articles: List<DigestArticleResponse>
)

/**
 * Raw upstream/source HTML for a digest article.
 */
data class DigestArticleSourceResponse(
    @SerializedName("digest_id") val digestId: String,
    @SerializedName("article_id") val articleId: String,
    @SerializedName("url") val url: String,
    @SerializedName("final_url") val finalUrl: String,
    @SerializedName("content_type") val contentType: String?,
    @SerializedName("fetched_at") val fetchedAt: String,
    @SerializedName("size_bytes") val sizeBytes: Long,
    @SerializedName("html") val html: String
)

// ===== Feed Sync Models =====

/**
 * Tombstone for a deleted feed (from server).
 */
data class FeedTombstoneResponse(
    @SerializedName("url") val url: String,
    @SerializedName("deleted_at") val deletedAt: String
)

/**
 * Response for feed changes (incremental sync).
 * Used for bi-directional feed sync with Ghostwriter.
 */
data class FeedChangesResponse(
    @SerializedName("feeds") val feeds: List<FeedResponse>,
    @SerializedName("tombstones") val tombstones: List<FeedTombstoneResponse>,
    @SerializedName("server_timestamp") val serverTimestamp: String
)

// ===== Client Config Models =====

/**
 * Status of an external integration (Wallabag, Newsletters, etc.)
 */
data class IntegrationStatus(
    @SerializedName("enabled") val enabled: Boolean,
    @SerializedName("label") val label: String? = null
)

/**
 * Preview article response for integrations like Wallabag/Newsletters.
 */
data class PreviewArticleResponse(
    @SerializedName("title") val title: String,
    @SerializedName("url") val url: String,
    @SerializedName("author") val author: String? = null,
    @SerializedName("word_count") val wordCount: Int? = null
)

/**
 * Generic preview response.
 */
data class PreviewResponse(
    @SerializedName("status") val status: String,
    @SerializedName("count") val count: Int = 0,
    @SerializedName("articles") val articles: List<PreviewArticleResponse> = emptyList(),
    @SerializedName("detail") val detail: String? = null
)

/**
 * Response for clear-seen operations.
 */
data class ClearSeenResponse(
    @SerializedName("cleared") val cleared: Int
)

/**
 * Media feed response (podcast or YouTube).
 */
data class MediaFeedResponse(
    @SerializedName("id") val id: String,
    @SerializedName("feed_type") val feedType: String,
    @SerializedName("url") val url: String,
    @SerializedName("resolved_feed_url") val resolvedFeedUrl: String?,
    @SerializedName("title") val title: String,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("mode") val mode: String,
    @SerializedName("max_items") val maxItems: Int,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String,
    @SerializedName("deleted_at") val deletedAt: String?
)

/**
 * Media processing status summary.
 */
data class MediaProcessingStatusResponse(
    @SerializedName("is_running") val isRunning: Boolean,
    @SerializedName("pending_count") val pendingCount: Int,
    @SerializedName("processing_count") val processingCount: Int,
    @SerializedName("completed_count") val completedCount: Int,
    @SerializedName("failed_count") val failedCount: Int,
    @SerializedName("current_item_title") val currentItemTitle: String?,
    @SerializedName("current_item_content_type") val currentItemContentType: String?,
    @SerializedName("last_completed_at") val lastCompletedAt: String?,
    @SerializedName("next_run_at") val nextRunAt: String?
)

/**
 * Media trigger response.
 */
data class MediaTriggerResponse(
    @SerializedName("status") val status: String,
    @SerializedName("detail") val detail: String? = null
)

/**
 * Media item summary (without full transcript content).
 */
data class MediaItemSummaryResponse(
    @SerializedName("id") val id: String,
    @SerializedName("media_feed_id") val mediaFeedId: String,
    @SerializedName("title") val title: String,
    @SerializedName("author") val author: String?,
    @SerializedName("content_type") val contentType: String,
    @SerializedName("mode") val mode: String,
    @SerializedName("word_count") val wordCount: Int,
    @SerializedName("is_summary") val isSummary: Boolean,
    @SerializedName("ai_failed") val aiFailed: Boolean,
    @SerializedName("status") val status: String,
    @SerializedName("error_message") val errorMessage: String?,
    @SerializedName("consumed_at") val consumedAt: String?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("completed_at") val completedAt: String?
)

/**
 * Server log file metadata.
 */
data class LogFileInfoResponse(
    @SerializedName("filename") val filename: String,
    @SerializedName("size_bytes") val sizeBytes: Long,
    @SerializedName("modified_at") val modifiedAt: String
)

/**
 * Response model for client configuration (shared settings).
 */
data class ClientConfigResponse(
    @SerializedName("min_word_count") val minWordCount: Int? = null,
    @SerializedName("morning_hour") val morningHour: Int? = null,
    @SerializedName("morning_minute") val morningMinute: Int? = null,
    @SerializedName("noon_hour") val noonHour: Int? = null,
    @SerializedName("noon_minute") val noonMinute: Int? = null,
    @SerializedName("evening_hour") val eveningHour: Int? = null,
    @SerializedName("evening_minute") val eveningMinute: Int? = null,
    @SerializedName("timezone") val timezone: String,
    // Legacy fields for backwards-compatible parsing against older servers.
    @SerializedName("schedule_morning") val scheduleMorning: String? = null,
    @SerializedName("schedule_noon") val scheduleNoon: String? = null,
    @SerializedName("schedule_evening") val scheduleEvening: String? = null,
    @SerializedName("whisper_provider") val whisperProvider: String? = null,
    @SerializedName("whisper_model") val whisperModel: String? = null,
    @SerializedName("whisper_timeout_minutes") val whisperTimeoutMinutes: Int? = null,
    @SerializedName("media_processing_interval_hours") val mediaProcessingIntervalHours: Int? = null,
    @SerializedName("include_podcasts_in_digest") val includePodcastsInDigest: Boolean? = null,
    @SerializedName("include_youtube_in_digest") val includeYoutubeInDigest: Boolean? = null,
    @SerializedName("cover_enabled") val coverEnabled: Boolean? = null,
    @SerializedName("cover_provider") val coverProvider: String? = null,
    @SerializedName("cover_quality") val coverQuality: String? = null,
    @SerializedName("cover_prompt") val coverPrompt: String? = null,
    @SerializedName("cover_overlay_enabled") val coverOverlayEnabled: Boolean? = null,
    @SerializedName("cover_openai_api_key") val coverOpenAiApiKey: String? = null,
    @SerializedName("cover_gemini_api_key") val coverGeminiApiKey: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    // Integration status
    @SerializedName("wallabag") val wallabag: IntegrationStatus? = null,
    @SerializedName("newsletters") val newsletters: IntegrationStatus? = null
)

/**
 * Request model for updating client configuration.
 */
data class ClientConfigUpdateRequest(
    @SerializedName("min_word_count") val minWordCount: Int? = null,
    @SerializedName("morning_hour") val morningHour: Int? = null,
    @SerializedName("morning_minute") val morningMinute: Int? = null,
    @SerializedName("noon_hour") val noonHour: Int? = null,
    @SerializedName("noon_minute") val noonMinute: Int? = null,
    @SerializedName("evening_hour") val eveningHour: Int? = null,
    @SerializedName("evening_minute") val eveningMinute: Int? = null,
    @SerializedName("timezone") val timezone: String? = null,
    // Legacy fields kept for compatibility with older server builds.
    @SerializedName("schedule_morning") val scheduleMorning: String? = null,
    @SerializedName("schedule_noon") val scheduleNoon: String? = null,
    @SerializedName("schedule_evening") val scheduleEvening: String? = null,
    @SerializedName("include_podcasts_in_digest") val includePodcastsInDigest: Boolean? = null,
    @SerializedName("include_youtube_in_digest") val includeYoutubeInDigest: Boolean? = null,
    @SerializedName("cover_enabled") val coverEnabled: Boolean? = null,
    @SerializedName("cover_overlay_enabled") val coverOverlayEnabled: Boolean? = null,
    @SerializedName("client_updated_at") val clientUpdatedAt: String? = null
)
