package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.delete
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.http.appendPathSegments
import io.ktor.http.ContentType

class GhostwriterApiClient(
    private val client: HttpClient,
    baseUrl: String,
    private val apiKey: String?
) {
    private val apiBaseUrl = normalizeApiBaseUrl(baseUrl)

    suspend fun performSync(feedSince: String? = null, digestIds: String? = null): SyncResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("sync") }
            authorize()
            feedSince?.let { parameter("feed_since", it) }
            digestIds?.let { parameter("digest_ids", it) }
        }
        return response.bodyOrThrow()
    }

    suspend fun getHealth(): HealthResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("health") }
        }
        return response.bodyOrThrow()
    }

    suspend fun listFeeds(): List<FeedResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("feeds") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun syncFeeds(feeds: List<FeedSyncRequest>): FeedSyncResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("feeds", "sync") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(feeds)
        }
        return response.bodyOrThrow()
    }

    suspend fun deleteFeedByUrl(feedUrl: String) {
        val response = client.delete(apiBaseUrl) {
            url { appendPathSegments("feeds", "by-url", feedUrl) }
            authorize()
        }
        response.requireSuccess()
    }

    suspend fun getFeedChanges(since: String? = null): FeedChangesResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("feeds", "changes") }
            authorize()
            since?.let { parameter("since", it) }
        }
        return response.bodyOrThrow()
    }

    suspend fun triggerDigest(request: DigestTriggerRequest): DigestTriggerResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("digests", "trigger") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun listDigests(): List<DigestResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("digests") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getLatestDigest(): DigestResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("digests", "latest") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getDigestStatus(digestId: String): DigestStatusResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("digests", digestId, "status") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getDigestArticles(digestId: String): DigestArticlesResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("digests", digestId, "articles") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getDigestArticleSource(digestId: String, articleId: String): DigestArticleSourceResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("digests", digestId, "articles", articleId, "source") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun listSchedules(): List<ScheduleResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("schedules") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun updateSchedule(period: String, request: ScheduleUpdateRequest): ScheduleResponse {
        val response = client.put(apiBaseUrl) {
            url { appendPathSegments("schedules", period) }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun sendHeartbeat(): HeartbeatResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("client", "heartbeat") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun getClientStatus(): ClientStatusResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("client", "status") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getConfig(): ClientConfigResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("config") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun updateConfig(request: ClientConfigUpdateRequest): ClientConfigResponse {
        val response = client.put(apiBaseUrl) {
            url { appendPathSegments("config") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun previewWallabag(): PreviewResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("config", "wallabag", "preview") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun previewNewsletters(): PreviewResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("newsletters", "preview") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun clearWallabagSeen(): ClearSeenResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("config", "wallabag", "clear-seen") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun clearNewsletterSeen(): ClearSeenResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("config", "newsletters", "clear-seen") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun getLogFiles(): List<LogFileInfoResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("logs") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun listAuthTokens(): List<AuthApiTokenResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("auth", "tokens") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun createAuthToken(name: String): AuthApiTokenCreateResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("auth", "tokens") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(AuthApiTokenCreateRequest(name))
        }
        return response.bodyOrThrow()
    }

    suspend fun revokeAuthToken(id: String): StatusMessageResponse {
        val response = client.delete(apiBaseUrl) {
            url { appendPathSegments("auth", "tokens", id) }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getMediaStatus(): MediaProcessingStatusResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "status") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun triggerMediaProcessing(): MediaTriggerResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("media", "trigger") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(emptyMap<String, String>())
        }
        return response.bodyOrThrow()
    }

    suspend fun getPodcastFeeds(): List<MediaFeedResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "podcasts") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun createPodcastFeed(request: MediaFeedCreateRequest): MediaFeedResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("media", "podcasts") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun updatePodcastFeed(feedId: String, request: MediaFeedUpdateRequest): MediaFeedResponse {
        val response = client.put(apiBaseUrl) {
            url { appendPathSegments("media", "podcasts", feedId) }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun deletePodcastFeed(feedId: String): StatusMessageResponse {
        val response = client.delete(apiBaseUrl) {
            url { appendPathSegments("media", "podcasts", feedId) }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getYouTubeFeeds(): List<MediaFeedResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "youtube") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun resolveYouTubeFeed(url: String): YouTubeResolveResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("media", "youtube", "resolve") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(YouTubeResolveRequest(url))
        }
        return response.bodyOrThrow()
    }

    suspend fun createYouTubeFeed(request: MediaFeedCreateRequest): MediaFeedResponse {
        val response = client.post(apiBaseUrl) {
            url { appendPathSegments("media", "youtube") }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun updateYouTubeFeed(feedId: String, request: MediaFeedUpdateRequest): MediaFeedResponse {
        val response = client.put(apiBaseUrl) {
            url { appendPathSegments("media", "youtube", feedId) }
            authorize()
            contentType(ContentType.Application.Json)
            setBody(request)
        }
        return response.bodyOrThrow()
    }

    suspend fun deleteYouTubeFeed(feedId: String): StatusMessageResponse {
        val response = client.delete(apiBaseUrl) {
            url { appendPathSegments("media", "youtube", feedId) }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getAllPodcastItems(): List<MediaItemSummaryResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "podcasts", "items", "all") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getAllYouTubeItems(): List<MediaItemSummaryResponse> {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "youtube", "items", "all") }
            authorize()
        }
        return response.bodyOrThrow()
    }

    suspend fun getMediaItem(id: String): MediaItemResponse {
        val response = client.get(apiBaseUrl) {
            url { appendPathSegments("media", "items", id) }
            authorize()
        }
        return response.bodyOrThrow()
    }

    private fun io.ktor.client.request.HttpRequestBuilder.authorize() {
        apiKey?.takeIf { it.isNotBlank() }?.let {
            header(HttpHeaders.Authorization, "Bearer $it")
        }
    }

    private suspend inline fun <reified T> io.ktor.client.statement.HttpResponse.bodyOrThrow(): T {
        requireSuccess()
        return body()
    }

    private fun io.ktor.client.statement.HttpResponse.requireSuccess() {
        if (!status.isSuccess()) {
            throw GhostwriterApiException.fromStatus(status)
        }
    }

    private fun normalizeApiBaseUrl(baseUrl: String): String {
        val trimmed = baseUrl.trim().trimEnd('/')
        return if (trimmed.endsWith("/api")) "$trimmed/" else "$trimmed/api/"
    }
}

sealed class GhostwriterApiException(message: String) : Exception(message) {
    data object Unauthorized : GhostwriterApiException("Unauthorized")
    data object NotFound : GhostwriterApiException("Not found")
    data object Conflict : GhostwriterApiException("Conflict")
    data object RateLimited : GhostwriterApiException("Rate limited")
    data class HttpError(val statusCode: Int) : GhostwriterApiException("HTTP $statusCode")

    companion object {
        fun fromStatus(status: HttpStatusCode): GhostwriterApiException {
            return when (status) {
                HttpStatusCode.Unauthorized -> Unauthorized
                HttpStatusCode.NotFound -> NotFound
                HttpStatusCode.Conflict -> Conflict
                HttpStatusCode.TooManyRequests -> RateLimited
                else -> HttpError(status.value)
            }
        }
    }
}
