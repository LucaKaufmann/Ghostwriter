package com.example.epilogue.shared.sync

import com.example.epilogue.shared.domain.Feed
import com.example.epilogue.shared.domain.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedChangesResponse
import com.example.epilogue.shared.ghostwriter.FeedResponse
import com.example.epilogue.shared.ghostwriter.FeedSyncRequest
import com.example.epilogue.shared.ghostwriter.FeedSyncResponse
import com.example.epilogue.shared.ghostwriter.FeedTombstoneResponse
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class FeedSyncUseCaseTest {
    @Test
    fun sync_appliesUpsertsTombstonesAndTimestamp() = runTest {
        val settings = FakeSettingsPort()
        val feedStore = FakeFeedStorePort(
            feeds = listOf(
                Feed(url = "https://local.feed", name = "Local", mode = ProcessingMode.FIDELITY)
            )
        )
        val ghostwriter = FakeGhostwriterSyncPort(
            syncFeedsResult = SyncPortResult.Success(FeedSyncResponse(1, 0, 0, 1)),
            feedChangesResult = SyncPortResult.Success(
                FeedChangesResponse(
                    feeds = listOf(
                        FeedResponse(
                            id = "1",
                            url = "https://server.feed",
                            title = "Server",
                            isActive = true,
                            mode = "raw",
                            maxArticles = 10,
                            createdAt = "2026-03-07T09:00:00Z",
                            updatedAt = "2026-03-07T09:30:00Z"
                        )
                    ),
                    tombstones = listOf(
                        FeedTombstoneResponse(url = "https://deleted.feed", deletedAt = "2026-03-07T09:45:00Z")
                    ),
                    serverTimestamp = "2026-03-07T10:00:00Z"
                )
            )
        )

        val useCase = FeedSyncUseCase(settings, feedStore, ghostwriter)
        val outcome = useCase.sync()

        val success = assertIs<FeedSyncOutcome.Success>(outcome)
        assertEquals(1, success.updatedFeeds)
        assertEquals(1, success.deletedFeeds)
        assertEquals(1, feedStore.upserted.size)
        assertEquals(listOf("https://deleted.feed"), feedStore.deletedUrls)
        assertEquals(1, feedStore.clearLocalModifiedCalls)
        assertEquals(1, ghostwriter.syncCalls)
        assertEquals("https://local.feed", ghostwriter.lastSyncedFeeds.first().url)
    }

    private class FakeSettingsPort : SettingsPort {
        var lastFeedSyncMillis: Long? = null

        override suspend fun isGhostwriterConfigured(): Boolean = true
        override suspend fun getConfigUpdatedAt(): String? = null
        override suspend fun setConfigUpdatedAt(value: String?) = Unit
        override suspend fun getMinWordCount(): Int = 0
        override suspend fun setMinWordCount(value: Int) = Unit
        override suspend fun getGhostwriterSchedule(): GhostwriterScheduleSnapshot? = null
        override suspend fun setGhostwriterSchedule(value: GhostwriterScheduleSnapshot) = Unit
        override suspend fun getLastFeedSyncTimeMillis(): Long? = lastFeedSyncMillis
        override suspend fun setLastFeedSyncTimeMillis(value: Long) {
            lastFeedSyncMillis = value
        }

        override suspend fun getLastDigestSyncTimeMillis(): Long? = null
        override suspend fun setLastDigestSyncTimeMillis(value: Long) = Unit
        override suspend fun shouldDownloadGhostwriterEpubsOnSync(): Boolean = true
    }

    private class FakeFeedStorePort(feeds: List<Feed>) : FeedStorePort {
        private val allFeeds = feeds.toMutableList()
        val upserted = mutableListOf<Feed>()
        var deletedUrls: List<String> = emptyList()
        var clearLocalModifiedCalls = 0

        override suspend fun getAllFeeds(): List<Feed> = allFeeds.toList()

        override suspend fun upsertAll(feeds: List<Feed>) {
            upserted.addAll(feeds)
        }

        override suspend fun deleteByUrls(urls: List<String>) {
            deletedUrls = urls
        }

        override suspend fun clearAllLocallyModified() {
            clearLocalModifiedCalls++
        }
    }

    private class FakeGhostwriterSyncPort(
        private val syncFeedsResult: SyncPortResult<FeedSyncResponse>,
        private val feedChangesResult: SyncPortResult<FeedChangesResponse>
    ) : GhostwriterSyncPort {
        var syncCalls = 0
        var lastSyncedFeeds: List<FeedSyncRequest> = emptyList()

        override suspend fun getConfig() = SyncPortResult.NotConfigured

        override suspend fun updateConfig(request: com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest) =
            SyncPortResult.NotConfigured

        override suspend fun syncFeeds(feeds: List<FeedSyncRequest>): SyncPortResult<FeedSyncResponse> {
            syncCalls++
            lastSyncedFeeds = feeds
            return syncFeedsResult
        }

        override suspend fun getFeedChanges(since: String?): SyncPortResult<FeedChangesResponse> = feedChangesResult

        override suspend fun performSync(feedSince: String?, digestIds: String?) = SyncPortResult.NotConfigured
        override suspend fun listDigests() = SyncPortResult.NotConfigured
        override suspend fun getDigestArticles(digestId: String) = SyncPortResult.NotConfigured
    }
}
