package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.ClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.shared.ghostwriter.DigestListResponse
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class ConfigSyncUseCaseTest {
    @Test
    fun serverNewer_appliesServerConfig() = runTest {
        val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T08:00:00Z")
        val ghostwriter = FakeGhostwriterSyncPort(
            configResult = SyncPortResult.Success(
                ClientConfigResponse(
                    minWordCount = 200,
                    morningHour = 6,
                    morningMinute = 30,
                    noonHour = 12,
                    noonMinute = 0,
                    eveningHour = 18,
                    eveningMinute = 0,
                    timezone = "UTC",
                    updatedAt = "2026-03-07T10:00:00Z"
                )
            )
        )

        val useCase = ConfigSyncUseCase(settings, ghostwriter)
        val ok = useCase.syncConfig()

        assertTrue(ok)
        assertEquals(200, settings.minWordCount)
        assertEquals(6, settings.schedule?.morningHour)
        assertEquals("2026-03-07T10:00:00Z", settings.configUpdatedAt)
    }

    @Test
    fun localNewer_pushesLocalConfig() = runTest {
        val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
        val ghostwriter = FakeGhostwriterSyncPort(
            configResult = SyncPortResult.Success(
                ClientConfigResponse(
                    timezone = "UTC",
                    updatedAt = "2026-03-07T09:00:00Z"
                )
            ),
            updateConfigResult = SyncPortResult.Success(
                ClientConfigResponse(timezone = "UTC", updatedAt = "2026-03-07T10:00:00Z")
            )
        )

        val useCase = ConfigSyncUseCase(settings, ghostwriter)
        val ok = useCase.syncConfig()

        assertTrue(ok)
        assertEquals(1, ghostwriter.updateConfigCalls)
    }

    @Test
    fun conflictOnPushMinWordCount_refetchesConfig() = runTest {
        val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
        val ghostwriter = FakeGhostwriterSyncPort(
            configResult = SyncPortResult.Success(
                ClientConfigResponse(
                    minWordCount = 150,
                    morningHour = 7,
                    morningMinute = 0,
                    noonHour = 12,
                    noonMinute = 0,
                    eveningHour = 18,
                    eveningMinute = 0,
                    timezone = "UTC",
                    updatedAt = "2026-03-07T11:00:00Z"
                )
            ),
            updateConfigResult = SyncPortResult.Error("conflict", code = 409)
        )

        val useCase = ConfigSyncUseCase(settings, ghostwriter)
        val ok = useCase.pushMinWordCount(250)

        assertTrue(!ok)
        assertEquals(1, ghostwriter.getConfigCalls)
        assertEquals(150, settings.minWordCount)
    }

    private class FakeSettingsPort(
        var configUpdatedAt: String? = null
    ) : SettingsPort {
        var minWordCount: Int = 100
        var schedule: GhostwriterScheduleSnapshot? = GhostwriterScheduleSnapshot(7, 0, 12, 0, 18, 0, "UTC")

        override suspend fun isGhostwriterConfigured(): Boolean = true

        override suspend fun getConfigUpdatedAt(): String? = configUpdatedAt

        override suspend fun setConfigUpdatedAt(value: String?) {
            configUpdatedAt = value
        }

        override suspend fun getMinWordCount(): Int = minWordCount

        override suspend fun setMinWordCount(value: Int) {
            minWordCount = value
        }

        override suspend fun getGhostwriterSchedule(): GhostwriterScheduleSnapshot? = schedule

        override suspend fun setGhostwriterSchedule(value: GhostwriterScheduleSnapshot) {
            schedule = value
        }

        override suspend fun getLastFeedSyncTimeMillis(): Long? = null
        override suspend fun setLastFeedSyncTimeMillis(value: Long) = Unit
        override suspend fun getLastDigestSyncTimeMillis(): Long? = null
        override suspend fun setLastDigestSyncTimeMillis(value: Long) = Unit
        override suspend fun shouldDownloadGhostwriterEpubsOnSync(): Boolean = true
    }

    private class FakeGhostwriterSyncPort(
        private val configResult: SyncPortResult<ClientConfigResponse> = SyncPortResult.NotConfigured,
        private val updateConfigResult: SyncPortResult<ClientConfigResponse> = SyncPortResult.NotConfigured
    ) : GhostwriterSyncPort {
        var getConfigCalls = 0
        var updateConfigCalls = 0

        override suspend fun getConfig(): SyncPortResult<ClientConfigResponse> {
            getConfigCalls++
            return configResult
        }

        override suspend fun updateConfig(request: ClientConfigUpdateRequest): SyncPortResult<ClientConfigResponse> {
            updateConfigCalls++
            return updateConfigResult
        }

        override suspend fun syncFeeds(feeds: List<com.example.epilogue.shared.ghostwriter.FeedSyncRequest>) = SyncPortResult.NotConfigured
        override suspend fun getFeedChanges(since: String?) = SyncPortResult.NotConfigured
        override suspend fun performSync(feedSince: String?, digestIds: String?) = SyncPortResult.NotConfigured
        override suspend fun listDigests(): SyncPortResult<DigestListResponse> = SyncPortResult.NotConfigured
        override suspend fun getDigestArticles(digestId: String) = SyncPortResult.NotConfigured
    }
}
