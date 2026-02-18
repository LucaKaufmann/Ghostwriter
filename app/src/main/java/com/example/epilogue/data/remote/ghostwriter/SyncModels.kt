package com.example.epilogue.data.remote.ghostwriter

import com.google.gson.annotations.SerializedName

/**
 * Combined sync response from GET /sync endpoint.
 * Contains all data the client needs in a single response.
 */
data class SyncResponse(
    @SerializedName("config") val config: ClientConfigResponse,
    @SerializedName("feeds") val feeds: FeedChangesResponse,
    @SerializedName("digests") val digests: SyncDigestsSection,
    @SerializedName("schedules") val schedules: List<ScheduleResponse>
)

/**
 * Digests section of the sync response.
 */
data class SyncDigestsSection(
    @SerializedName("new_digests") val newDigests: List<SyncDigest>
)

/**
 * Digest with embedded articles from the sync endpoint.
 */
data class SyncDigest(
    @SerializedName("id") val id: String,
    @SerializedName("filename") val filename: String,
    @SerializedName("available_formats") val availableFormats: List<String>? = null,
    @SerializedName("period") val period: String,
    @SerializedName("status") val status: String,
    @SerializedName("stage") val stage: String?,
    @SerializedName("article_count") val articleCount: Int,
    @SerializedName("error_message") val errorMessage: String?,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("completed_at") val completedAt: String?,
    @SerializedName("articles") val articles: List<DigestArticleResponse>
)
