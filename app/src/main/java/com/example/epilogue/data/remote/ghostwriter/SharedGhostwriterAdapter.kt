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
import com.example.epilogue.shared.ghostwriter.AuthApiTokenCreateResponse as SharedAuthApiTokenCreateResponse
import com.example.epilogue.shared.ghostwriter.AuthApiTokenResponse as SharedAuthApiTokenResponse
import com.example.epilogue.shared.ghostwriter.DigestArticleSourceResponse as SharedDigestArticleSourceResponse
import com.example.epilogue.shared.ghostwriter.DigestArticlesResponse as SharedDigestArticlesResponse
import com.example.epilogue.shared.ghostwriter.DigestProgress as SharedDigestProgress
import com.example.epilogue.shared.ghostwriter.DigestStatusResponse as SharedDigestStatusResponse
import com.example.epilogue.shared.ghostwriter.DigestTriggerRequest as SharedDigestTriggerRequest
import com.example.epilogue.shared.ghostwriter.DigestTriggerResponse as SharedDigestTriggerResponse
import com.example.epilogue.shared.ghostwriter.FeedSyncRequest as SharedFeedSyncRequest
import com.example.epilogue.shared.ghostwriter.FeedSyncResponse as SharedFeedSyncResponse
import com.example.epilogue.shared.ghostwriter.HealthResponse as SharedHealthResponse
import com.example.epilogue.shared.ghostwriter.DigestArticleResponse as SharedDigestArticleResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse as SharedDigestResponse
import com.example.epilogue.shared.ghostwriter.FeedChangesResponse as SharedFeedChangesResponse
import com.example.epilogue.shared.ghostwriter.FeedResponse as SharedFeedResponse
import com.example.epilogue.shared.ghostwriter.FeedTombstoneResponse as SharedFeedTombstoneResponse
import com.example.epilogue.shared.ghostwriter.HeartbeatResponse as SharedHeartbeatResponse
import com.example.epilogue.shared.ghostwriter.IntegrationStatus as SharedIntegrationStatus
import com.example.epilogue.shared.ghostwriter.LogFileInfoResponse as SharedLogFileInfoResponse
import com.example.epilogue.shared.ghostwriter.MediaFeedCreateRequest as SharedMediaFeedCreateRequest
import com.example.epilogue.shared.ghostwriter.MediaFeedResponse as SharedMediaFeedResponse
import com.example.epilogue.shared.ghostwriter.MediaFeedUpdateRequest as SharedMediaFeedUpdateRequest
import com.example.epilogue.shared.ghostwriter.MediaItemResponse as SharedMediaItemResponse
import com.example.epilogue.shared.ghostwriter.MediaItemSummaryResponse as SharedMediaItemSummaryResponse
import com.example.epilogue.shared.ghostwriter.MediaProcessingStatusResponse as SharedMediaProcessingStatusResponse
import com.example.epilogue.shared.ghostwriter.MediaTriggerResponse as SharedMediaTriggerResponse
import com.example.epilogue.shared.ghostwriter.PreviewArticleResponse as SharedPreviewArticleResponse
import com.example.epilogue.shared.ghostwriter.PreviewResponse as SharedPreviewResponse
import com.example.epilogue.shared.ghostwriter.ScheduleResponse as SharedScheduleResponse
import com.example.epilogue.shared.ghostwriter.ScheduleUpdateRequest as SharedScheduleUpdateRequest
import com.example.epilogue.shared.ghostwriter.StatusMessageResponse as SharedStatusMessageResponse
import com.example.epilogue.shared.ghostwriter.SyncDigest as SharedSyncDigest
import com.example.epilogue.shared.ghostwriter.SyncDigestsSection as SharedSyncDigestsSection
import com.example.epilogue.shared.ghostwriter.SyncResponse as SharedSyncResponse
import com.example.epilogue.shared.ghostwriter.YouTubeResolveResponse as SharedYouTubeResolveResponse

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

    suspend fun checkHealth(): HealthResponse {
        return client.getHealth().toApp()
    }

    suspend fun syncFeeds(feeds: List<FeedSyncRequest>): FeedSyncResponse {
        return client.syncFeeds(feeds.map { it.toShared() }).toApp()
    }

    suspend fun deleteFeedByUrl(feedUrl: String) {
        client.deleteFeedByUrl(feedUrl)
    }

    suspend fun triggerDigest(period: String): DigestTriggerResponse {
        return client.triggerDigest(SharedDigestTriggerRequest(period = period)).toApp()
    }

    suspend fun getDigestStatus(digestId: String): DigestStatusResponse {
        return client.getDigestStatus(digestId).toApp()
    }

    suspend fun getDigestArticles(digestId: String): DigestArticlesResponse {
        return client.getDigestArticles(digestId).toApp()
    }

    suspend fun getDigestArticleSource(digestId: String, articleId: String): DigestArticleSourceResponse {
        return client.getDigestArticleSource(digestId, articleId).toApp()
    }

    suspend fun getLatestDigest(): DigestResponse {
        return client.getLatestDigest().toApp()
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

    suspend fun getLogFiles(): List<LogFileInfoResponse> {
        return client.getLogFiles().map { it.toApp() }
    }

    suspend fun listAuthTokens(): List<AuthApiTokenResponse> {
        return client.listAuthTokens().map { it.toApp() }
    }

    suspend fun createAuthToken(name: String): AuthApiTokenCreateResponse {
        return client.createAuthToken(name).toApp()
    }

    suspend fun revokeAuthToken(id: String): StatusMessageResponse {
        return client.revokeAuthToken(id).toApp()
    }

    suspend fun getMediaStatus(): MediaProcessingStatusResponse {
        return client.getMediaStatus().toApp()
    }

    suspend fun triggerMediaProcessing(): MediaTriggerResponse {
        return client.triggerMediaProcessing().toApp()
    }

    suspend fun getPodcastFeeds(): List<MediaFeedResponse> {
        return client.getPodcastFeeds().map { it.toApp() }
    }

    suspend fun createPodcastFeed(request: MediaFeedCreateRequest): MediaFeedResponse {
        return client.createPodcastFeed(request.toShared()).toApp()
    }

    suspend fun updatePodcastFeed(feedId: String, request: MediaFeedUpdateRequest): MediaFeedResponse {
        return client.updatePodcastFeed(feedId, request.toShared()).toApp()
    }

    suspend fun deletePodcastFeed(feedId: String): StatusMessageResponse {
        return client.deletePodcastFeed(feedId).toApp()
    }

    suspend fun getYouTubeFeeds(): List<MediaFeedResponse> {
        return client.getYouTubeFeeds().map { it.toApp() }
    }

    suspend fun resolveYouTubeFeed(url: String): YouTubeResolveResponse {
        return client.resolveYouTubeFeed(url).toApp()
    }

    suspend fun createYouTubeFeed(request: MediaFeedCreateRequest): MediaFeedResponse {
        return client.createYouTubeFeed(request.toShared()).toApp()
    }

    suspend fun updateYouTubeFeed(feedId: String, request: MediaFeedUpdateRequest): MediaFeedResponse {
        return client.updateYouTubeFeed(feedId, request.toShared()).toApp()
    }

    suspend fun deleteYouTubeFeed(feedId: String): StatusMessageResponse {
        return client.deleteYouTubeFeed(feedId).toApp()
    }

    suspend fun getAllPodcastItems(): List<MediaItemSummaryResponse> {
        return client.getAllPodcastItems().map { it.toApp() }
    }

    suspend fun getAllYouTubeItems(): List<MediaItemSummaryResponse> {
        return client.getAllYouTubeItems().map { it.toApp() }
    }

    suspend fun getMediaItem(id: String): MediaItemResponse {
        return client.getMediaItem(id).toApp()
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

private fun SharedDigestArticlesResponse.toApp(): DigestArticlesResponse = DigestArticlesResponse(
    digestId = digestId,
    articleCount = articleCount,
    articles = articles.map { it.toApp() }
)

private fun SharedDigestArticleSourceResponse.toApp(): DigestArticleSourceResponse = DigestArticleSourceResponse(
    digestId = digestId,
    articleId = articleId,
    url = url,
    finalUrl = finalUrl,
    contentType = contentType,
    fetchedAt = fetchedAt,
    sizeBytes = sizeBytes,
    html = html
)

private fun SharedDigestProgress.toApp(): DigestProgress = DigestProgress(
    totalFeeds = totalFeeds,
    feedsFetched = feedsFetched,
    totalArticles = totalArticles,
    articlesEnriched = articlesEnriched
)

private fun SharedDigestStatusResponse.toApp(): DigestStatusResponse = DigestStatusResponse(
    id = id,
    status = status,
    stage = stage,
    progress = progress.toApp(),
    startedAt = startedAt,
    etaSeconds = etaSeconds
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

private fun SharedLogFileInfoResponse.toApp(): LogFileInfoResponse = LogFileInfoResponse(
    filename = filename,
    sizeBytes = sizeBytes,
    modifiedAt = modifiedAt
)

private fun SharedAuthApiTokenResponse.toApp(): AuthApiTokenResponse = AuthApiTokenResponse(
    id = id,
    name = name,
    tokenPrefix = tokenPrefix,
    createdAt = createdAt,
    lastUsedAt = lastUsedAt,
    revokedAt = revokedAt
)

private fun SharedAuthApiTokenCreateResponse.toApp(): AuthApiTokenCreateResponse = AuthApiTokenCreateResponse(
    id = id,
    name = name,
    token = token,
    tokenPrefix = tokenPrefix,
    createdAt = createdAt
)

private fun SharedStatusMessageResponse.toApp(): StatusMessageResponse = StatusMessageResponse(
    status = status,
    message = message
)

private fun SharedHealthResponse.toApp(): HealthResponse = HealthResponse(
    status = status,
    version = version,
    uptimeSeconds = uptimeSeconds,
    lastSuccessfulDigest = lastSuccessfulDigest,
    aiProvider = aiProvider,
    aiModel = aiModel
)

private fun FeedSyncRequest.toShared(): SharedFeedSyncRequest = SharedFeedSyncRequest(
    url = url,
    title = title,
    isActive = isActive,
    mode = mode,
    maxArticles = maxArticles
)

private fun SharedFeedSyncResponse.toApp(): FeedSyncResponse = FeedSyncResponse(
    synced = synced,
    created = created,
    updated = updated,
    unchanged = unchanged
)

private fun SharedDigestTriggerResponse.toApp(): DigestTriggerResponse = DigestTriggerResponse(
    id = id,
    status = status,
    message = message
)

private fun SharedMediaProcessingStatusResponse.toApp(): MediaProcessingStatusResponse = MediaProcessingStatusResponse(
    isRunning = isRunning,
    pendingCount = pendingCount,
    processingCount = processingCount,
    completedCount = completedCount,
    failedCount = failedCount,
    currentItemTitle = currentItemTitle,
    currentItemContentType = currentItemContentType,
    lastCompletedAt = lastCompletedAt,
    nextRunAt = nextRunAt
)

private fun SharedMediaTriggerResponse.toApp(): MediaTriggerResponse = MediaTriggerResponse(
    status = status,
    detail = detail
)

private fun SharedMediaFeedResponse.toApp(): MediaFeedResponse = MediaFeedResponse(
    id = id,
    feedType = feedType,
    url = url,
    resolvedFeedUrl = resolvedFeedUrl,
    title = title,
    isActive = isActive,
    mode = mode,
    maxItems = maxItems,
    createdAt = createdAt,
    updatedAt = updatedAt,
    deletedAt = deletedAt
)

private fun MediaFeedCreateRequest.toShared(): SharedMediaFeedCreateRequest = SharedMediaFeedCreateRequest(
    feedType = feedType,
    url = url,
    resolvedFeedUrl = resolvedFeedUrl,
    title = title,
    isActive = isActive,
    mode = mode,
    maxItems = maxItems
)

private fun MediaFeedUpdateRequest.toShared(): SharedMediaFeedUpdateRequest = SharedMediaFeedUpdateRequest(
    title = title,
    isActive = isActive,
    mode = mode,
    maxItems = maxItems
)

private fun SharedYouTubeResolveResponse.toApp(): YouTubeResolveResponse = YouTubeResolveResponse(
    rssFeedUrl = rssFeedUrl,
    channelId = channelId,
    channelTitle = channelTitle
)

private fun SharedMediaItemSummaryResponse.toApp(): MediaItemSummaryResponse = MediaItemSummaryResponse(
    id = id,
    mediaFeedId = mediaFeedId,
    title = title,
    author = author,
    contentType = contentType,
    mode = mode,
    wordCount = wordCount,
    isSummary = isSummary,
    aiFailed = aiFailed,
    status = status,
    errorMessage = errorMessage,
    consumedAt = consumedAt,
    createdAt = createdAt,
    completedAt = completedAt
)

private fun SharedMediaItemResponse.toApp(): MediaItemResponse = MediaItemResponse(
    id = id,
    mediaFeedId = mediaFeedId,
    guid = guid,
    url = url,
    contentUrl = contentUrl,
    title = title,
    author = author,
    content = content,
    contentType = contentType,
    mode = mode,
    wordCount = wordCount,
    isSummary = isSummary,
    aiFailed = aiFailed,
    processingMs = processingMs,
    status = status,
    errorMessage = errorMessage,
    consumedAt = consumedAt,
    consumedDigestId = consumedDigestId,
    createdAt = createdAt,
    completedAt = completedAt
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
