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
 * Response model for client configuration (shared settings).
 */
data class ClientConfigResponse(
    @SerializedName("timezone") val timezone: String,
    @SerializedName("ai_provider") val aiProvider: String? = null,
    @SerializedName("ai_model") val aiModel: String? = null,
    @SerializedName("schedule_enabled") val scheduleEnabled: Boolean? = null,
    @SerializedName("schedule_morning") val scheduleMorning: String? = null,
    @SerializedName("schedule_noon") val scheduleNoon: String? = null,
    @SerializedName("schedule_evening") val scheduleEvening: String? = null,
    @SerializedName("digest_retention_days") val digestRetentionDays: Int? = null,
    @SerializedName("max_articles_per_digest") val maxArticlesPerDigest: Int? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    // Integration status
    @SerializedName("wallabag") val wallabag: IntegrationStatus? = null,
    @SerializedName("newsletters") val newsletters: IntegrationStatus? = null
)

// ===== Push Notification Models =====

data class PushDeviceRegisterRequest(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("platform") val platform: String, // ios | android
    @SerializedName("token") val token: String,
    @SerializedName("app_version") val appVersion: String? = null,
    @SerializedName("device_model") val deviceModel: String? = null
)

data class PushDeviceResponse(
    @SerializedName("id") val id: String,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("platform") val platform: String,
    @SerializedName("enabled") val enabled: Boolean,
    @SerializedName("disabled_at") val disabledAt: String? = null,
    @SerializedName("app_version") val appVersion: String? = null,
    @SerializedName("device_model") val deviceModel: String? = null,
    @SerializedName("last_seen_at") val lastSeenAt: String,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String
)

data class StatusResponse(
    @SerializedName("status") val status: String,
    @SerializedName("message") val message: String? = null
)

/**
 * Request model for updating client configuration.
 */
data class ClientConfigUpdateRequest(
    @SerializedName("timezone") val timezone: String? = null,
    @SerializedName("schedule_enabled") val scheduleEnabled: Boolean? = null,
    @SerializedName("schedule_morning") val scheduleMorning: String? = null,
    @SerializedName("schedule_noon") val scheduleNoon: String? = null,
    @SerializedName("schedule_evening") val scheduleEvening: String? = null,
    @SerializedName("client_updated_at") val clientUpdatedAt: String? = null
)
