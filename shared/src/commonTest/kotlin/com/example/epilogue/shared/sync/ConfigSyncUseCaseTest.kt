package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.ClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.shared.ghostwriter.DigestListResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
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

    @Test
    fun localNewer_failedOrUnavailablePushRemainsPending() = runTest {
        val timestamp = "2026-03-07T10:00:00Z"
        for (failure in listOf(SyncPortResult.Error("offline"), SyncPortResult.NotConfigured)) {
            val settings = FakeSettingsPort(configUpdatedAt = timestamp)
            val remote = FakeGhostwriterSyncPort(
                configResult = SyncPortResult.Success(config("2026-03-07T09:00:00Z", 200)),
                updateConfigResult = failure
            )
            assertFalse(ConfigSyncUseCase(settings, remote).syncConfig())
            assertEquals(timestamp, settings.configUpdatedAt)
            assertEquals(100, settings.minWordCount)
            assertEquals(1, remote.updateConfigCalls)
        }
    }

    @Test
    fun localNewer_conflictRefetchSuccessReconcilesServer() = runTest {
        val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
        val remote = FakeGhostwriterSyncPort(
            configResult = SyncPortResult.Success(config("2026-03-07T09:00:00Z", 200)),
            updateConfigResult = SyncPortResult.Error("conflict", code = 409),
            refetchConfigResult = SyncPortResult.Success(config("2026-03-07T11:00:00Z", 250))
        )
        assertTrue(ConfigSyncUseCase(settings, remote).syncConfig())
        assertEquals(2, remote.getConfigCalls)
        assertEquals(250, settings.minWordCount)
        assertEquals("2026-03-07T11:00:00Z", settings.configUpdatedAt)
    }

    @Test
    fun localNewer_conflictRefetchFailurePreservesLocalState() = runTest {
        val timestamp = "2026-03-07T10:00:00Z"
        val settings = FakeSettingsPort(configUpdatedAt = timestamp)
        val remote = FakeGhostwriterSyncPort(
            configResult = SyncPortResult.Success(config("2026-03-07T09:00:00Z", 200)),
            updateConfigResult = SyncPortResult.Error("conflict", code = 409),
            refetchConfigResult = SyncPortResult.Error("offline")
        )
        assertFalse(ConfigSyncUseCase(settings, remote).syncConfig())
        assertEquals(2, remote.getConfigCalls)
        assertEquals(timestamp, settings.configUpdatedAt)
        assertEquals(100, settings.minWordCount)
    }

    @Test
    fun prefetchedLocalNewerUsesGuardedPushAndReportsFailure() = runTest {
        val timestamp = "2026-03-07T10:00:00Z"
        val settings = FakeSettingsPort(configUpdatedAt = timestamp)
        val remote = FakeGhostwriterSyncPort(updateConfigResult = SyncPortResult.Error("offline"))
        assertFalse(ConfigSyncUseCase(settings, remote).applyPreFetchedConfig(config("2026-03-07T09:00:00Z", 200)))
        assertEquals(timestamp, settings.configUpdatedAt)
        assertEquals(100, settings.minWordCount)

        remote.updateConfigResult = SyncPortResult.Success(config("2026-03-07T12:00:00Z", 100))
        assertTrue(ConfigSyncUseCase(settings, remote).applyPreFetchedConfig(config("2026-03-07T09:00:00Z", 200)))
        assertEquals("2026-03-07T12:00:00Z", settings.configUpdatedAt)
        assertEquals(2, remote.updateConfigCalls)
    }

    @Test
    fun prefetchedEqualAndServerNewerApplyWithoutPush() = runTest {
        val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
        val remote = FakeGhostwriterSyncPort()
        val useCase = ConfigSyncUseCase(settings, remote)
        assertTrue(useCase.applyPreFetchedConfig(config("2026-03-07T10:00:00Z", 150)))
        assertEquals(150, settings.minWordCount)
        assertTrue(useCase.applyPreFetchedConfig(config("2026-03-07T11:00:00Z", 200)))
        assertEquals(200, settings.minWordCount)
        assertEquals(0, remote.updateConfigCalls)
    }

    @Test
    fun localNewerUsesObservedServerVersionForBothEntryPoints() = runTest {
        for (prefetched in listOf(false, true)) {
            val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
            val remote = FakeGhostwriterSyncPort().apply {
                serverConfig = config("2026-03-07T09:00:00Z", 200)
            }
            val useCase = ConfigSyncUseCase(settings, remote)

            val synced = if (prefetched) {
                useCase.applyPreFetchedConfig(remote.serverConfig!!)
            } else {
                useCase.syncConfig()
            }

            assertTrue(synced)
            assertEquals("2026-03-07T09:00:00Z", remote.lastUpdateRequest?.clientUpdatedAt)
            assertEquals(100, remote.lastUpdateRequest?.minWordCount)
            assertEquals(7, remote.lastUpdateRequest?.morningHour)
            assertEquals(100, remote.serverConfig?.minWordCount)
            assertEquals("2026-03-07T12:00:00Z", settings.configUpdatedAt)
        }
    }

    @Test
    fun actualConcurrentServerChangeConflictsAndRefetchesOnBothEntryPoints() = runTest {
        for (prefetched in listOf(false, true)) {
            val settings = FakeSettingsPort(configUpdatedAt = "2026-03-07T10:00:00Z")
            val remote = FakeGhostwriterSyncPort().apply {
                serverConfig = config("2026-03-07T09:00:00Z", 200)
                onUpdateConfig = { serverConfig = config("2026-03-07T11:00:00Z", 300) }
            }
            val useCase = ConfigSyncUseCase(settings, remote)

            val reconciled = if (prefetched) {
                useCase.applyPreFetchedConfig(remote.serverConfig!!)
            } else {
                useCase.syncConfig()
            }

            assertTrue(reconciled)
            assertEquals("2026-03-07T09:00:00Z", remote.lastUpdateRequest?.clientUpdatedAt)
            assertEquals(if (prefetched) 1 else 2, remote.getConfigCalls)
            assertEquals(300, settings.minWordCount)
            assertEquals("2026-03-07T11:00:00Z", settings.configUpdatedAt)
        }
    }

    @Test
    fun editDuringSuccessfulUploadRemainsPending() = runTest {
        for (prefetched in listOf(false, true)) {
            val timestamp = "2026-03-07T10:00:00Z"
            val settings = FakeSettingsPort(configUpdatedAt = timestamp)
            val remote = FakeGhostwriterSyncPort().apply {
                serverConfig = config("2026-03-07T09:00:00Z", 200)
                onUpdateConfig = {
                    if (prefetched) {
                        settings.schedule = GhostwriterScheduleSnapshot(8, 0, 12, 0, 18, 0, "UTC")
                    } else {
                        settings.configUpdatedAt = "2026-03-07T13:00:00Z"
                    }
                }
            }
            val useCase = ConfigSyncUseCase(settings, remote)

            val synced = if (prefetched) {
                useCase.applyPreFetchedConfig(remote.serverConfig!!)
            } else {
                useCase.syncConfig()
            }

            assertFalse(synced)
            assertEquals(100, remote.lastUpdateRequest?.minWordCount)
            assertEquals(if (prefetched) 8 else 7, settings.schedule?.morningHour)
            assertEquals(if (prefetched) timestamp else "2026-03-07T13:00:00Z", settings.configUpdatedAt)
        }
    }

    @Test
    fun editDuringConflictRefetchIsNotOverwritten() = runTest {
        for (prefetched in listOf(false, true)) {
            val timestamp = "2026-03-07T10:00:00Z"
            val settings = FakeSettingsPort(configUpdatedAt = timestamp)
            val remote = FakeGhostwriterSyncPort().apply {
                serverConfig = config("2026-03-07T09:00:00Z", 200)
                onUpdateConfig = { serverConfig = config("2026-03-07T11:00:00Z", 300) }
                onGetConfig = { count ->
                    if (count == (if (prefetched) 1 else 2)) settings.minWordCount = 400
                }
            }
            val useCase = ConfigSyncUseCase(settings, remote)

            val reconciled = if (prefetched) {
                useCase.applyPreFetchedConfig(remote.serverConfig!!)
            } else {
                useCase.syncConfig()
            }

            assertFalse(reconciled)
            assertEquals(400, settings.minWordCount)
            assertEquals(timestamp, settings.configUpdatedAt)
            assertEquals(300, remote.serverConfig?.minWordCount)
        }
    }

    @Test
    fun saveErrorAndCancellationNeverBecomeSuccess() = runTest {
        val timestamp = "2026-03-07T10:00:00Z"
        val settings = FakeSettingsPort(configUpdatedAt = timestamp, failSetConfigUpdatedAt = true)
        val remote = FakeGhostwriterSyncPort(
            updateConfigResult = SyncPortResult.Success(config("2026-03-07T12:00:00Z", 100))
        )
        assertFailsWith<IllegalStateException> {
            ConfigSyncUseCase(settings, remote).applyPreFetchedConfig(config("2026-03-07T09:00:00Z", 200))
        }
        assertEquals(timestamp, settings.configUpdatedAt)

        remote.updateConfigError = CancellationException("cancelled")
        assertFailsWith<CancellationException> {
            ConfigSyncUseCase(settings, remote).applyPreFetchedConfig(config("2026-03-07T09:00:00Z", 200))
        }
        assertEquals(timestamp, settings.configUpdatedAt)
    }

    private fun config(updatedAt: String, minWordCount: Int): ClientConfigResponse =
        ClientConfigResponse(minWordCount = minWordCount, timezone = "UTC", updatedAt = updatedAt)

    private class FakeSettingsPort(
        var configUpdatedAt: String? = null,
        private val failSetConfigUpdatedAt: Boolean = false
    ) : SettingsPort {
        var minWordCount: Int = 100
        var schedule: GhostwriterScheduleSnapshot? = GhostwriterScheduleSnapshot(7, 0, 12, 0, 18, 0, "UTC")

        override suspend fun isGhostwriterConfigured(): Boolean = true

        override suspend fun getConfigUpdatedAt(): String? = configUpdatedAt

        override suspend fun setConfigUpdatedAt(value: String?) {
            if (failSetConfigUpdatedAt) throw IllegalStateException("save failed")
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
        var updateConfigResult: SyncPortResult<ClientConfigResponse> = SyncPortResult.NotConfigured,
        private val refetchConfigResult: SyncPortResult<ClientConfigResponse> = configResult,
        var updateConfigError: Throwable? = null
    ) : GhostwriterSyncPort {
        var getConfigCalls = 0
        var updateConfigCalls = 0
        var serverConfig: ClientConfigResponse? = null
        var lastUpdateRequest: ClientConfigUpdateRequest? = null
        var onUpdateConfig: (() -> Unit)? = null
        var onGetConfig: ((Int) -> Unit)? = null

        override suspend fun getConfig(): SyncPortResult<ClientConfigResponse> {
            getConfigCalls++
            onGetConfig?.invoke(getConfigCalls)
            serverConfig?.let { return SyncPortResult.Success(it) }
            return if (getConfigCalls == 1) configResult else refetchConfigResult
        }

        override suspend fun updateConfig(request: ClientConfigUpdateRequest): SyncPortResult<ClientConfigResponse> {
            updateConfigCalls++
            lastUpdateRequest = request
            updateConfigError?.let { throw it }
            onUpdateConfig?.invoke()
            serverConfig?.let { server ->
                val serverTime = parseIso8601ToEpochMillis(server.updatedAt)!!
                val clientTime = parseIso8601ToEpochMillis(request.clientUpdatedAt)
                if (clientTime == null || abs(serverTime - clientTime) > 1_000L) {
                    return SyncPortResult.Error("conflict", code = 409)
                }
                val updated = server.copy(
                    minWordCount = request.minWordCount,
                    morningHour = request.morningHour,
                    morningMinute = request.morningMinute,
                    updatedAt = "2026-03-07T12:00:00Z"
                )
                serverConfig = updated
                return SyncPortResult.Success(updated)
            }
            return updateConfigResult
        }

        override suspend fun syncFeeds(feeds: List<com.example.epilogue.shared.ghostwriter.FeedSyncRequest>) = SyncPortResult.NotConfigured
        override suspend fun getFeedChanges(since: String?) = SyncPortResult.NotConfigured
        override suspend fun performSync(feedSince: String?, digestIds: String?) = SyncPortResult.NotConfigured
        override suspend fun listDigests(): SyncPortResult<DigestListResponse> = SyncPortResult.NotConfigured
        override suspend fun getDigestArticles(digestId: String) = SyncPortResult.NotConfigured
    }
}
