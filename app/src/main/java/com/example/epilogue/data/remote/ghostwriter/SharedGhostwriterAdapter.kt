package com.example.epilogue.data.remote.ghostwriter

import com.example.epilogue.shared.ghostwriter.GhostwriterApiClient
import io.ktor.client.HttpClient
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json
import com.example.epilogue.shared.ghostwriter.ClientConfigResponse as SharedClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest as SharedClientConfigUpdateRequest
import com.example.epilogue.shared.ghostwriter.ClientStatusResponse as SharedClientStatusResponse
import com.example.epilogue.shared.ghostwriter.ClearSeenResponse as SharedClearSeenResponse
import com.example.epilogue.shared.ghostwriter.DigestArticleResponse as SharedDigestArticleResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse as SharedDigestResponse
import com.example.epilogue.shared.ghostwriter.FeedChangesResponse as SharedFeedChangesResponse
import com.example.epilogue.shared.ghostwriter.FeedResponse as SharedFeedResponse
import com.example.epilogue.shared.ghostwriter.FeedTombstoneResponse as SharedFeedTombstoneResponse
import com.example.epilogue.shared.ghostwriter.HeartbeatResponse as SharedHeartbeatResponse
import com.example.epilogue.shared.ghostwriter.IntegrationStatus as SharedIntegrationStatus
import com.example.epilogue.shared.ghostwriter.PreviewArticleResponse as SharedPreviewArticleResponse
import com.example.epilogue.shared.ghostwriter.PreviewResponse as SharedPreviewResponse
import com.example.epilogue.shared.ghostwriter.ScheduleResponse as SharedScheduleResponse
import com.example.epilogue.shared.ghostwriter.ScheduleUpdateRequest as SharedScheduleUpdateRequest
import com.example.epilogue.shared.ghostwriter.SyncDigest as SharedSyncDigest
import com.example.epilogue.shared.ghostwriter.SyncDigestsSection as SharedSyncDigestsSection
import com.example.epilogue.shared.ghostwriter.SyncResponse as SharedSyncResponse

/**
 * Thin adapter around shared KMP GhostwriterApiClient.
 * Maps shared DTOs back to existing Android app DTOs.
 */
class SharedGhostwriterAdapter private constructor(
    private val httpClient: HttpClient,
    private val client: GhostwriterApiClient
) {
    suspend fun performSync(feedSince: String?, digestIds: String?): SyncResponse {
        return client.performSync(feedSince = feedSince, digestIds = digestIds).toApp()
    }

    suspend fun getFeedChanges(since: String?): FeedChangesResponse {
        return client.getFeedChanges(since = since).toApp()
    }

    suspend fun listDigests(): List<DigestResponse> {
        return client.listDigests().map { it.toApp() }
    }

    suspend fun updateConfig(request: ClientConfigUpdateRequest): ClientConfigResponse {
        return client.updateConfig(request.toShared()).toApp()
    }

    suspend fun getConfig(): ClientConfigResponse {
        return client.getConfig().toApp()
    }

    suspend fun getClientStatus(): ClientStatusResponse {
        return client.getClientStatus().toApp()
    }

    suspend fun sendHeartbeat(): HeartbeatResponse {
        return client.sendHeartbeat().toApp()
    }

    suspend fun getSchedules(): List<ScheduleResponse> {
        return client.listSchedules().map { it.toApp() }
    }

    suspend fun updateSchedule(period: String, request: ScheduleUpdateRequest): ScheduleResponse {
        return client.updateSchedule(
            period = period,
            request = request.toShared()
        ).toApp()
    }

    suspend fun previewWallabag(): PreviewResponse {
        return client.previewWallabag().toApp()
    }

    suspend fun previewNewsletters(): PreviewResponse {
        return client.previewNewsletters().toApp()
    }

    suspend fun clearWallabagSeen(): ClearSeenResponse {
        return client.clearWallabagSeen().toApp()
    }

    suspend fun clearNewsletterSeen(): ClearSeenResponse {
        return client.clearNewsletterSeen().toApp()
    }

    fun close() {
        httpClient.close()
    }

    companion object {
        fun create(baseUrl: String, apiKey: String?): SharedGhostwriterAdapter {
            val httpClient = HttpClient(OkHttp) {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
            }

            val apiClient = GhostwriterApiClient(
                client = httpClient,
                baseUrl = baseUrl,
                apiKey = apiKey
            )

            return SharedGhostwriterAdapter(httpClient = httpClient, client = apiClient)
        }

        internal fun fromClient(httpClient: HttpClient, client: GhostwriterApiClient): SharedGhostwriterAdapter {
            return SharedGhostwriterAdapter(httpClient = httpClient, client = client)
        }
    }
}

private fun SharedSyncResponse.toApp(): SyncResponse = SyncResponse(
    config = config.toApp(),
    feeds = feeds.toApp(),
    digests = digests.toApp(),
    schedules = schedules.map { it.toApp() }
)

private fun SharedSyncDigestsSection.toApp(): SyncDigestsSection = SyncDigestsSection(
    newDigests = newDigests.map { it.toApp() }
)

private fun SharedSyncDigest.toApp(): SyncDigest = SyncDigest(
    id = id,
    filename = filename,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt,
    articles = articles.map { it.toApp() }
)

private fun SharedFeedChangesResponse.toApp(): FeedChangesResponse = FeedChangesResponse(
    feeds = feeds.map { it.toApp() },
    tombstones = tombstones.map { it.toApp() },
    serverTimestamp = serverTimestamp
)

private fun SharedFeedResponse.toApp(): FeedResponse = FeedResponse(
    id = id,
    url = url,
    title = title,
    isActive = isActive,
    mode = mode,
    maxArticles = maxArticles,
    createdAt = createdAt,
    updatedAt = updatedAt
)

private fun SharedFeedTombstoneResponse.toApp(): FeedTombstoneResponse = FeedTombstoneResponse(
    url = url,
    deletedAt = deletedAt
)

private fun SharedDigestResponse.toApp(): DigestResponse = DigestResponse(
    id = id,
    filename = filename,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt
)

private fun SharedDigestArticleResponse.toApp(): DigestArticleResponse = DigestArticleResponse(
    id = id,
    title = title,
    url = url,
    mode = mode,
    wordCount = wordCount,
    content = content,
    author = author,
    feedTitle = feedTitle,
    sortOrder = sortOrder,
    aiFailed = aiFailed
)

private fun SharedScheduleResponse.toApp(): ScheduleResponse = ScheduleResponse(
    id = id,
    period = period,
    hour = hour,
    minute = minute,
    enabled = enabled,
    timezone = timezone,
    nextRunAt = nextRunAt
)

private fun SharedClientConfigResponse.toApp(): ClientConfigResponse = ClientConfigResponse(
    minWordCount = minWordCount,
    morningHour = morningHour,
    morningMinute = morningMinute,
    noonHour = noonHour,
    noonMinute = noonMinute,
    eveningHour = eveningHour,
    eveningMinute = eveningMinute,
    timezone = timezone,
    scheduleMorning = scheduleMorning,
    scheduleNoon = scheduleNoon,
    scheduleEvening = scheduleEvening,
    whisperProvider = whisperProvider,
    whisperModel = whisperModel,
    whisperTimeoutMinutes = whisperTimeoutMinutes,
    mediaProcessingIntervalHours = mediaProcessingIntervalHours,
    includePodcastsInDigest = includePodcastsInDigest,
    includeYoutubeInDigest = includeYoutubeInDigest,
    coverEnabled = coverEnabled,
    coverProvider = coverProvider,
    coverQuality = coverQuality,
    coverPrompt = coverPrompt,
    coverOverlayEnabled = coverOverlayEnabled,
    coverOpenAiApiKey = coverOpenAiApiKey,
    coverGeminiApiKey = coverGeminiApiKey,
    updatedAt = updatedAt,
    wallabag = wallabag?.toApp(),
    newsletters = newsletters?.toApp()
)

private fun SharedIntegrationStatus.toApp(): IntegrationStatus = IntegrationStatus(
    enabled = enabled,
    label = label
)

private fun SharedClientStatusResponse.toApp(): ClientStatusResponse = ClientStatusResponse(
    lastHeartbeatAt = lastHeartbeatAt,
    lastDownloadAt = lastDownloadAt,
    autoDisableEnabled = autoDisableEnabled,
    autoDisableAfterDays = autoDisableAfterDays,
    schedulesAutoDisabled = schedulesAutoDisabled,
    daysUntilAutoDisable = daysUntilAutoDisable
)

private fun SharedHeartbeatResponse.toApp(): HeartbeatResponse = HeartbeatResponse(
    status = status,
    receivedAt = receivedAt,
    schedulesActive = schedulesActive,
    message = message
)

private fun ScheduleUpdateRequest.toShared(): SharedScheduleUpdateRequest = SharedScheduleUpdateRequest(
    hour = hour,
    minute = minute,
    enabled = enabled,
    timezone = timezone
)

private fun SharedPreviewResponse.toApp(): PreviewResponse = PreviewResponse(
    status = status,
    count = count,
    articles = articles.map { it.toApp() },
    detail = detail
)

private fun SharedPreviewArticleResponse.toApp(): PreviewArticleResponse = PreviewArticleResponse(
    title = title,
    url = url,
    author = author,
    wordCount = wordCount
)

private fun SharedClearSeenResponse.toApp(): ClearSeenResponse = ClearSeenResponse(
    cleared = cleared
)

private fun ClientConfigUpdateRequest.toShared(): SharedClientConfigUpdateRequest = SharedClientConfigUpdateRequest(
    minWordCount = minWordCount,
    morningHour = morningHour,
    morningMinute = morningMinute,
    noonHour = noonHour,
    noonMinute = noonMinute,
    eveningHour = eveningHour,
    eveningMinute = eveningMinute,
    timezone = timezone,
    scheduleMorning = scheduleMorning,
    scheduleNoon = scheduleNoon,
    scheduleEvening = scheduleEvening,
    includePodcastsInDigest = includePodcastsInDigest,
    includeYoutubeInDigest = includeYoutubeInDigest,
    coverEnabled = coverEnabled,
    coverProvider = coverProvider,
    coverQuality = coverQuality,
    coverPrompt = coverPrompt,
    coverOverlayEnabled = coverOverlayEnabled,
    clientUpdatedAt = clientUpdatedAt
)
