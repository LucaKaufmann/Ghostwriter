package com.example.epilogue.shared.sync

import com.example.epilogue.shared.domain.Feed
import com.example.epilogue.shared.ghostwriter.ClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.shared.ghostwriter.DigestArticlesResponse
import com.example.epilogue.shared.ghostwriter.DigestListResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse
import com.example.epilogue.shared.ghostwriter.FeedChangesResponse
import com.example.epilogue.shared.ghostwriter.FeedSyncRequest
import com.example.epilogue.shared.ghostwriter.FeedSyncResponse
import com.example.epilogue.shared.ghostwriter.SyncResponse

sealed class SyncPortResult<out T> {
    data class Success<T>(val data: T) : SyncPortResult<T>()
    data class Error(val message: String, val code: Int? = null) : SyncPortResult<Nothing>()
    data object NotConfigured : SyncPortResult<Nothing>()
}

data class GhostwriterScheduleSnapshot(
    val morningHour: Int,
    val morningMinute: Int,
    val noonHour: Int,
    val noonMinute: Int,
    val eveningHour: Int,
    val eveningMinute: Int,
    val timezone: String
)

interface SettingsPort {
    suspend fun isGhostwriterConfigured(): Boolean

    suspend fun getConfigUpdatedAt(): String?
    suspend fun setConfigUpdatedAt(value: String?)

    suspend fun getMinWordCount(): Int
    suspend fun setMinWordCount(value: Int)

    suspend fun getGhostwriterSchedule(): GhostwriterScheduleSnapshot?
    suspend fun setGhostwriterSchedule(value: GhostwriterScheduleSnapshot)

    suspend fun getLastFeedSyncTimeMillis(): Long?
    suspend fun setLastFeedSyncTimeMillis(value: Long)

    suspend fun getLastDigestSyncTimeMillis(): Long?
    suspend fun setLastDigestSyncTimeMillis(value: Long)

    suspend fun shouldDownloadGhostwriterEpubsOnSync(): Boolean
}

interface FeedStorePort {
    suspend fun getAllFeeds(): List<Feed>
    suspend fun upsertAll(feeds: List<Feed>)
    suspend fun deleteByUrls(urls: List<String>)
    suspend fun clearAllLocallyModified()
}

interface DigestStorePort {
    suspend fun getAllRemoteIds(): List<String>
}

interface GhostwriterSyncPort {
    suspend fun getConfig(): SyncPortResult<ClientConfigResponse>
    suspend fun updateConfig(request: ClientConfigUpdateRequest): SyncPortResult<ClientConfigResponse>

    suspend fun syncFeeds(feeds: List<FeedSyncRequest>): SyncPortResult<FeedSyncResponse>
    suspend fun getFeedChanges(since: String?): SyncPortResult<FeedChangesResponse>

    suspend fun performSync(feedSince: String?, digestIds: String?): SyncPortResult<SyncResponse>
    suspend fun listDigests(): SyncPortResult<DigestListResponse>
    suspend fun getDigestArticles(digestId: String): SyncPortResult<DigestArticlesResponse>
}
