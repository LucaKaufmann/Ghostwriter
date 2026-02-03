package com.example.epilogue.service

import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ConfigSyncManagerTest {

    private val settingsRepository: SettingsRepository = mockk(relaxed = true)
    private val ghostwriterRepository: GhostwriterRepository = mockk(relaxed = true)
    private val manager = ConfigSyncManager(settingsRepository, ghostwriterRepository)

    @Test
    fun `syncConfig returns false when ghostwriter not configured`() = runTest {
        every { settingsRepository.isGhostwriterConfigured() } returns false

        val result = manager.syncConfig()

        assertFalse(result)
        coVerify(exactly = 0) { ghostwriterRepository.getConfig() }
    }

    @Test
    fun `syncConfig applies server config on first sync`() = runTest {
        every { settingsRepository.isGhostwriterConfigured() } returns true
        every { settingsRepository.getConfigUpdatedAt() } returns null

        val serverConfig = ClientConfigResponse(
            timezone = "UTC",
            scheduleMorning = "07:30",
            scheduleNoon = "12:15",
            scheduleEvening = "18:45",
            updatedAt = "2025-01-01T00:00:00"
        )
        coEvery { ghostwriterRepository.getConfig() } returns GhostwriterResult.Success(serverConfig)

        val result = manager.syncConfig()

        assertTrue(result)
        verify {
            settingsRepository.setGhostwriterSchedule(
                morningHour = 7,
                morningMinute = 30,
                noonHour = 12,
                noonMinute = 15,
                eveningHour = 18,
                eveningMinute = 45,
                timezone = "UTC"
            )
        }
        coVerify { settingsRepository.setConfigUpdatedAt("2025-01-01T00:00:00") }
    }

    @Test
    fun `syncConfig pushes local config when local is newer`() = runTest {
        every { settingsRepository.isGhostwriterConfigured() } returns true
        every { settingsRepository.getConfigUpdatedAt() } returns "2025-02-01T00:00:00"
        every { settingsRepository.getGhostwriterSchedule() } returns SettingsRepository.GhostwriterSchedule(
            morningHour = 7,
            morningMinute = 30,
            noonHour = 12,
            noonMinute = 15,
            eveningHour = 18,
            eveningMinute = 45,
            timezone = "UTC"
        )

        val serverConfig = ClientConfigResponse(
            timezone = "UTC",
            scheduleMorning = "07:00",
            scheduleNoon = "12:00",
            scheduleEvening = "18:00",
            updatedAt = "2025-01-01T00:00:00"
        )
        coEvery { ghostwriterRepository.getConfig() } returns GhostwriterResult.Success(serverConfig)
        coEvery {
            ghostwriterRepository.updateConfig(
                timezone = "UTC",
                scheduleMorning = "07:30",
                scheduleNoon = "12:15",
                scheduleEvening = "18:45",
                clientUpdatedAt = "2025-02-01T00:00:00"
            )
        } returns GhostwriterResult.Success(serverConfig.copy(updatedAt = "2025-02-01T00:00:00"))

        val result = manager.syncConfig()

        assertTrue(result)
        coVerify {
            ghostwriterRepository.updateConfig(
                timezone = "UTC",
                scheduleMorning = "07:30",
                scheduleNoon = "12:15",
                scheduleEvening = "18:45",
                clientUpdatedAt = "2025-02-01T00:00:00"
            )
        }
        coVerify { settingsRepository.setConfigUpdatedAt("2025-02-01T00:00:00") }
    }
}
