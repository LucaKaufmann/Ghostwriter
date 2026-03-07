package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.DigestArticleResponse
import com.example.epilogue.shared.ghostwriter.DigestListResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse
import com.example.epilogue.shared.ghostwriter.SyncDigest
import com.example.epilogue.shared.ghostwriter.SyncDigestsSection
import com.example.epilogue.shared.ghostwriter.SyncResponse
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class DigestSyncUseCaseTest {
    @Test
    fun planSync_prefersCombinedSync() = runTest {
        val settings = FakeSettingsPort()
        val digestStore = FakeDigestStorePort(listOf("known-1"))
        val ghostwriter = FakeGhostwriterSyncPort(
            performSyncResult = SyncPortResult.Success(
                SyncResponse(
                    config = com.example.epilogue.shared.ghostwriter.ClientConfigResponse(timezone = "UTC"),
                    feeds = com.example.epilogue.shared.ghostwriter.FeedChangesResponse(emptyList(), emptyList(), "2026-03-07T10:00:00Z"),
                    digests = SyncDigestsSection(
                        newDigests = listOf(
                            SyncDigest(
                                id = "new-1",
                                filename = "new-1.epub",
                                period = "manual",
                                status = "completed",
                                articleCount = 1,
                                createdAt = "2026-03-07T10:00:00Z",
                                articles = listOf(
                                    DigestArticleResponse(
                                        id = "a1",
                                        title = "A1",
                                        url = "https://example.com/a1",
                                        mode = "raw",
                                        wordCount = 10,
                                        content = "x",
                                        author = null,
                                        feedTitle = "Feed",
                                        sortOrder = 0,
                                        aiFailed = false
                                    )
                                )
                            )
                        )
                    ),
                    schedules = emptyList()
                )
            )
        )

        val useCase = DigestSyncUseCase(settings, digestStore, ghostwriter)
        val plan = useCase.planSync()

        val combined = assertIs<DigestSyncPlan.Combined>(plan)
        assertEquals(1, combined.digests.size)
        assertEquals("new-1", combined.digests.first().id)
    }

    @Test
    fun planSync_fallsBackToLegacyWhenCombinedFails() = runTest {
        val settings = FakeSettingsPort()
        val digestStore = FakeDigestStorePort(listOf("known-1"))
        val ghostwriter = FakeGhostwriterSyncPort(
            performSyncResult = SyncPortResult.Error("nope"),
            listDigestsResult = SyncPortResult.Success(
                DigestListResponse(
                    digests = listOf(
                    DigestResponse(
                        id = "known-1",
                        filename = "known.epub",
                        period = "manual",
                        status = "completed",
                        articleCount = 1,
                        createdAt = "2026-03-07T10:00:00Z"
                    ),
                    DigestResponse(
                        id = "new-2",
                        filename = "new.epub",
                        period = "manual",
                        status = "completed",
                        articleCount = 2,
                        createdAt = "2026-03-07T10:00:00Z"
                    )
                    )
                )
            )
        )

        val useCase = DigestSyncUseCase(settings, digestStore, ghostwriter)
        val plan = useCase.planSync()

        val legacy = assertIs<DigestSyncPlan.Legacy>(plan)
        assertEquals(1, legacy.digests.size)
        assertEquals("new-2", legacy.digests.first().id)
    }

    private class FakeSettingsPort : SettingsPort {
        override suspend fun isGhostwriterConfigured(): Boolean = true
        override suspend fun getConfigUpdatedAt(): String? = null
        override suspend fun setConfigUpdatedAt(value: String?) = Unit
        override suspend fun getMinWordCount(): Int = 0
        override suspend fun setMinWordCount(value: Int) = Unit
        override suspend fun getGhostwriterSchedule(): GhostwriterScheduleSnapshot? = null
        override suspend fun setGhostwriterSchedule(value: GhostwriterScheduleSnapshot) = Unit
        override suspend fun getLastFeedSyncTimeMillis(): Long? = null
        override suspend fun setLastFeedSyncTimeMillis(value: Long) = Unit
        override suspend fun getLastDigestSyncTimeMillis(): Long? = null
        override suspend fun setLastDigestSyncTimeMillis(value: Long) = Unit
        override suspend fun shouldDownloadGhostwriterEpubsOnSync(): Boolean = true
    }

    private class FakeDigestStorePort(
        private val remoteIds: List<String>
    ) : DigestStorePort {
        override suspend fun getAllRemoteIds(): List<String> = remoteIds
    }

    private class FakeGhostwriterSyncPort(
        private val performSyncResult: SyncPortResult<SyncResponse>,
        private val listDigestsResult: SyncPortResult<DigestListResponse> = SyncPortResult.NotConfigured
    ) : GhostwriterSyncPort {
        override suspend fun getConfig() = SyncPortResult.NotConfigured

        override suspend fun updateConfig(request: com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest) =
            SyncPortResult.NotConfigured

        override suspend fun syncFeeds(feeds: List<com.example.epilogue.shared.ghostwriter.FeedSyncRequest>) =
            SyncPortResult.NotConfigured

        override suspend fun getFeedChanges(since: String?) = SyncPortResult.NotConfigured

        override suspend fun performSync(feedSince: String?, digestIds: String?): SyncPortResult<SyncResponse> =
            performSyncResult

        override suspend fun listDigests(): SyncPortResult<DigestListResponse> = listDigestsResult

        override suspend fun getDigestArticles(digestId: String) = SyncPortResult.NotConfigured
    }
}
