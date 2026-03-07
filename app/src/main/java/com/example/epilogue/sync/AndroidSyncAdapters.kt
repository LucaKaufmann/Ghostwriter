package com.example.epilogue.sync

import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.remote.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.data.remote.ghostwriter.DigestResponse
import com.example.epilogue.data.remote.ghostwriter.FeedChangesResponse
import com.example.epilogue.data.remote.ghostwriter.FeedSyncRequest
import com.example.epilogue.data.remote.ghostwriter.SyncResponse
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.domain.Feed as SharedFeed
import com.example.epilogue.shared.domain.ProcessingMode as SharedProcessingMode
import com.example.epilogue.shared.ghostwriter.ClientConfigResponse as SharedClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest as SharedClientConfigUpdateRequest
import com.example.epilogue.shared.ghostwriter.DigestArticleResponse as SharedDigestArticleResponse
import com.example.epilogue.shared.ghostwriter.DigestArticlesResponse as SharedDigestArticlesResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse as SharedDigestResponse
import com.example.epilogue.shared.ghostwriter.FeedChangesResponse as SharedFeedChangesResponse
import com.example.epilogue.shared.ghostwriter.FeedResponse as SharedFeedResponse
import com.example.epilogue.shared.ghostwriter.FeedSyncRequest as SharedFeedSyncRequest
import com.example.epilogue.shared.ghostwriter.FeedSyncResponse as SharedFeedSyncResponse
import com.example.epilogue.shared.ghostwriter.FeedTombstoneResponse as SharedFeedTombstoneResponse
import com.example.epilogue.shared.ghostwriter.SyncDigest as SharedSyncDigest
import com.example.epilogue.shared.ghostwriter.SyncDigestsSection as SharedSyncDigestsSection
import com.example.epilogue.shared.ghostwriter.SyncResponse as SharedSyncResponse
import com.example.epilogue.shared.sync.DigestStorePort
import com.example.epilogue.shared.sync.FeedStorePort
import com.example.epilogue.shared.sync.GhostwriterScheduleSnapshot
import com.example.epilogue.shared.sync.GhostwriterSyncPort
import com.example.epilogue.shared.sync.SettingsPort
import com.example.epilogue.shared.sync.SyncPortResult
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class AndroidSettingsPort @Inject constructor(
    private val settingsRepository: SettingsRepository
) : SettingsPort {
    override suspend fun isGhostwriterConfigured(): Boolean = settingsRepository.isGhostwriterConfigured()

    override suspend fun getConfigUpdatedAt(): String? = settingsRepository.getConfigUpdatedAt()

    override suspend fun setConfigUpdatedAt(value: String?) {
        settingsRepository.setConfigUpdatedAt(value)
    }

    override suspend fun getMinWordCount(): Int = settingsRepository.getMinWordCount()

    override suspend fun setMinWordCount(value: Int) {
        settingsRepository.setMinWordCount(value)
    }

    override suspend fun getGhostwriterSchedule(): GhostwriterScheduleSnapshot? {
        val schedule = settingsRepository.getGhostwriterSchedule() ?: return null
        return GhostwriterScheduleSnapshot(
            morningHour = schedule.morningHour,
            morningMinute = schedule.morningMinute,
            noonHour = schedule.noonHour,
            noonMinute = schedule.noonMinute,
            eveningHour = schedule.eveningHour,
            eveningMinute = schedule.eveningMinute,
            timezone = schedule.timezone
        )
    }

    override suspend fun setGhostwriterSchedule(value: GhostwriterScheduleSnapshot) {
        settingsRepository.setGhostwriterSchedule(
            morningHour = value.morningHour,
            morningMinute = value.morningMinute,
            noonHour = value.noonHour,
            noonMinute = value.noonMinute,
            eveningHour = value.eveningHour,
            eveningMinute = value.eveningMinute,
            timezone = value.timezone
        )
    }

    override suspend fun getLastFeedSyncTimeMillis(): Long? {
        val value = settingsRepository.getLastFeedSyncTime()
        return if (value > 0) value else null
    }

    override suspend fun setLastFeedSyncTimeMillis(value: Long) {
        settingsRepository.setLastFeedSyncTime(value)
    }

    override suspend fun getLastDigestSyncTimeMillis(): Long? {
        val value = settingsRepository.getLastDigestSyncTime()
        return if (value > 0) value else null
    }

    override suspend fun setLastDigestSyncTimeMillis(value: Long) {
        settingsRepository.setLastDigestSyncTime(value)
    }

    override suspend fun shouldDownloadGhostwriterEpubsOnSync(): Boolean {
        return settingsRepository.shouldDownloadGhostwriterEpubsOnSync()
    }
}

@Singleton
class AndroidFeedStorePort @Inject constructor(
    private val feedRepository: FeedRepository
) : FeedStorePort {
    override suspend fun getAllFeeds(): List<SharedFeed> {
        return feedRepository.getAllFeedsList().map { it.toShared() }
    }

    override suspend fun upsertAll(feeds: List<SharedFeed>) {
        feedRepository.upsertAll(feeds.map { it.toApp() })
    }

    override suspend fun deleteByUrls(urls: List<String>) {
        feedRepository.deleteByUrls(urls)
    }

    override suspend fun clearAllLocallyModified() {
        feedRepository.clearAllLocallyModified()
    }
}

@Singleton
class AndroidDigestStorePort @Inject constructor(
    private val digestRepository: DigestRepository
) : DigestStorePort {
    override suspend fun getAllRemoteIds(): List<String> = digestRepository.getAllRemoteIds()
}

@Singleton
class AndroidGhostwriterSyncPort @Inject constructor(
    private val ghostwriterRepository: GhostwriterRepository
) : GhostwriterSyncPort {
    override suspend fun getConfig(): SyncPortResult<SharedClientConfigResponse> {
        return when (val result = ghostwriterRepository.getConfig()) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(result.data.toShared())
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun updateConfig(request: SharedClientConfigUpdateRequest): SyncPortResult<SharedClientConfigResponse> {
        return when (
            val result = ghostwriterRepository.updateConfig(
                minWordCount = request.minWordCount,
                morningHour = request.morningHour,
                morningMinute = request.morningMinute,
                noonHour = request.noonHour,
                noonMinute = request.noonMinute,
                eveningHour = request.eveningHour,
                eveningMinute = request.eveningMinute,
                timezone = request.timezone,
                scheduleMorning = request.scheduleMorning,
                scheduleNoon = request.scheduleNoon,
                scheduleEvening = request.scheduleEvening,
                includePodcastsInDigest = request.includePodcastsInDigest,
                includeYoutubeInDigest = request.includeYoutubeInDigest,
                coverEnabled = request.coverEnabled,
                coverProvider = request.coverProvider,
                coverQuality = request.coverQuality,
                coverPrompt = request.coverPrompt,
                coverOverlayEnabled = request.coverOverlayEnabled,
                clientUpdatedAt = request.clientUpdatedAt
            )
        ) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(result.data.toShared())
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun syncFeeds(feeds: List<SharedFeedSyncRequest>): SyncPortResult<SharedFeedSyncResponse> {
        val appFeeds = feeds.map { it.toAppDomainFeed() }
        return when (val result = ghostwriterRepository.syncFeeds(appFeeds)) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(
                SharedFeedSyncResponse(
                    synced = result.data.synced,
                    created = result.data.created,
                    updated = result.data.updated,
                    unchanged = result.data.unchanged
                )
            )
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun getFeedChanges(since: String?): SyncPortResult<SharedFeedChangesResponse> {
        val sinceMillis = com.example.epilogue.shared.sync.parseIso8601ToEpochMillis(since)
        return when (val result = ghostwriterRepository.getFeedChanges(sinceMillis)) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(result.data.toShared())
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun performSync(feedSince: String?, digestIds: String?): SyncPortResult<SharedSyncResponse> {
        val feedSinceMillis = com.example.epilogue.shared.sync.parseIso8601ToEpochMillis(feedSince)
        val knownDigestIds = digestIds
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?: emptyList()

        return when (val result = ghostwriterRepository.performSync(feedSinceMillis, knownDigestIds)) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(result.data.toShared())
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun listDigests(): SyncPortResult<List<SharedDigestResponse>> {
        return when (val result = ghostwriterRepository.listDigests()) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(result.data.map { it.toShared() })
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }

    override suspend fun getDigestArticles(digestId: String): SyncPortResult<SharedDigestArticlesResponse> {
        return when (val result = ghostwriterRepository.getDigestArticles(digestId)) {
            is GhostwriterRepository.GhostwriterResult.Success -> SyncPortResult.Success(
                SharedDigestArticlesResponse(
                    digestId = result.data.digestId,
                    articleCount = result.data.articleCount,
                    articles = result.data.articles.map { article ->
                        SharedDigestArticleResponse(
                            id = article.id,
                            title = article.title,
                            url = article.url,
                            mode = article.mode,
                            wordCount = article.wordCount,
                            content = article.content,
                            contentHtml = article.contentHtml,
                            author = article.author,
                            feedTitle = article.feedTitle,
                            sortOrder = article.sortOrder,
                            aiFailed = article.aiFailed
                        )
                    }
                )
            )
            is GhostwriterRepository.GhostwriterResult.Error -> SyncPortResult.Error(result.message, result.code)
            is GhostwriterRepository.GhostwriterResult.NotConfigured -> SyncPortResult.NotConfigured
        }
    }
}

private fun Feed.toShared(): SharedFeed = SharedFeed(
    url = url,
    name = name,
    mode = when (mode) {
        ProcessingMode.BRIEFING -> SharedProcessingMode.BRIEFING
        ProcessingMode.FIDELITY -> SharedProcessingMode.FIDELITY
    },
    lastFetchedEpochMillis = lastFetched,
    maxArticles = maxArticles,
    isEnabled = isEnabled,
    serverUpdatedAtEpochMillis = serverUpdatedAt,
    locallyModified = locallyModified
)

private fun SharedFeed.toApp(): Feed = Feed(
    url = url,
    name = name,
    mode = when (mode) {
        SharedProcessingMode.BRIEFING -> ProcessingMode.BRIEFING
        SharedProcessingMode.FIDELITY -> ProcessingMode.FIDELITY
    },
    lastFetched = lastFetchedEpochMillis,
    maxArticles = maxArticles,
    isEnabled = isEnabled,
    serverUpdatedAt = serverUpdatedAtEpochMillis,
    locallyModified = locallyModified
)

private fun SharedFeedSyncRequest.toAppDomainFeed(): Feed {
    return Feed(
        url = url,
        name = title,
        mode = when (mode) {
            "summarize" -> ProcessingMode.BRIEFING
            else -> ProcessingMode.FIDELITY
        },
        maxArticles = maxArticles,
        isEnabled = isActive,
        locallyModified = false
    )
}

private fun FeedChangesResponse.toShared(): SharedFeedChangesResponse = SharedFeedChangesResponse(
    feeds = feeds.map { it.toShared() },
    tombstones = tombstones.map {
        SharedFeedTombstoneResponse(url = it.url, deletedAt = it.deletedAt)
    },
    serverTimestamp = serverTimestamp
)

private fun com.example.epilogue.data.remote.ghostwriter.FeedResponse.toShared(): SharedFeedResponse =
    SharedFeedResponse(
        id = id,
        url = url,
        title = title,
        isActive = isActive,
        mode = mode,
        maxArticles = maxArticles,
        createdAt = createdAt,
        updatedAt = updatedAt,
        deletedAt = deletedAt
    )

private fun ClientConfigResponse.toShared(): SharedClientConfigResponse = SharedClientConfigResponse(
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
    pdfEnabled = pdfEnabled,
    pdfPageSize = pdfPageSize,
    coverEnabled = coverEnabled,
    coverProvider = coverProvider,
    coverQuality = coverQuality,
    coverPrompt = coverPrompt,
    coverOverlayEnabled = coverOverlayEnabled,
    coverOpenAiApiKey = coverOpenAiApiKey,
    coverGeminiApiKey = coverGeminiApiKey,
    updatedAt = updatedAt,
    wallabag = wallabag?.let { com.example.epilogue.shared.ghostwriter.IntegrationStatus(it.enabled, it.label) },
    newsletters = newsletters?.let { com.example.epilogue.shared.ghostwriter.IntegrationStatus(it.enabled, it.label) }
)

private fun SyncResponse.toShared(): SharedSyncResponse = SharedSyncResponse(
    config = config.toShared(),
    feeds = feeds.toShared(),
    digests = SharedSyncDigestsSection(
        newDigests = digests.newDigests.map { it.toShared() }
    ),
    schedules = schedules.map {
        com.example.epilogue.shared.ghostwriter.ScheduleResponse(
            id = it.id,
            period = it.period,
            hour = it.hour,
            minute = it.minute,
            enabled = it.enabled,
            timezone = it.timezone,
            nextRunAt = it.nextRunAt
        )
    }
)

private fun com.example.epilogue.data.remote.ghostwriter.SyncDigest.toShared(): SharedSyncDigest = SharedSyncDigest(
    id = id,
    filename = filename,
    availableFormats = availableFormats,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt,
    articles = articles.map { article ->
        SharedDigestArticleResponse(
            id = article.id,
            title = article.title,
            url = article.url,
            mode = article.mode,
            wordCount = article.wordCount,
            content = article.content,
            contentHtml = article.contentHtml,
            author = article.author,
            feedTitle = article.feedTitle,
            sortOrder = article.sortOrder,
            aiFailed = article.aiFailed
        )
    }
)

private fun DigestResponse.toShared(): SharedDigestResponse = SharedDigestResponse(
    id = id,
    filename = filename,
    availableFormats = availableFormats,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt
)
