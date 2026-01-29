package com.example.epilogue.service

import android.util.Log
import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages configuration sync between the app and Ghostwriter backend.
 *
 * Sync happens on app startup with last-write-wins conflict resolution:
 * - If server config is newer, apply server config locally
 * - If local config is newer, push local config to server
 */
@Singleton
class ConfigSyncManager @Inject constructor(
    private val settingsRepository: SettingsRepository,
    private val ghostwriterRepository: GhostwriterRepository
) {
    companion object {
        private const val TAG = "ConfigSyncManager"
    }

    /**
     * Sync configuration with the server.
     * Should be called on app startup when Ghostwriter is enabled.
     *
     * @return true if sync was successful, false otherwise
     */
    suspend fun syncConfig(): Boolean = withContext(Dispatchers.IO) {
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.d(TAG, "Ghostwriter not configured, skipping config sync")
            return@withContext false
        }

        Log.i(TAG, "Starting config sync...")

        // Get server config
        val serverResult = ghostwriterRepository.getConfig()
        when (serverResult) {
            is GhostwriterResult.Success -> {
                val serverConfig = serverResult.data
                val localUpdatedAt = settingsRepository.getConfigUpdatedAt()

                if (localUpdatedAt == null) {
                    // First sync - apply server config
                    Log.i(TAG, "First sync, applying server config")
                    applyServerConfig(serverConfig)
                    return@withContext true
                }

                // Compare timestamps
                val serverUpdatedAt = serverConfig.updatedAt
                if (serverUpdatedAt == null) {
                    // Server doesn't provide updated_at, just apply
                    Log.i(TAG, "Server has no updated_at, applying server config")
                    applyServerConfig(serverConfig)
                    return@withContext true
                }
                val serverTime = parseTimestamp(serverUpdatedAt)
                val localTime = parseTimestamp(localUpdatedAt)

                when {
                    serverTime > localTime -> {
                        // Server is newer - apply server config
                        Log.i(TAG, "Server config is newer, applying")
                        applyServerConfig(serverConfig)
                    }
                    localTime > serverTime -> {
                        // Local is newer - push to server
                        Log.i(TAG, "Local config is newer, pushing to server")
                        pushLocalConfig(localUpdatedAt)
                    }
                    else -> {
                        Log.i(TAG, "Config is in sync")
                    }
                }
                return@withContext true
            }
            is GhostwriterResult.Error -> {
                Log.e(TAG, "Failed to get server config: ${serverResult.message}")
                return@withContext false
            }
            is GhostwriterResult.NotConfigured -> {
                Log.d(TAG, "Ghostwriter not configured")
                return@withContext false
            }
        }
    }

    /**
     * Apply server configuration to local settings.
     */
    private suspend fun applyServerConfig(config: ClientConfigResponse) {
        // Parse schedule times from "HH:mm" strings
        val morning = parseTime(config.scheduleMorning)
        val noon = parseTime(config.scheduleNoon)
        val evening = parseTime(config.scheduleEvening)

        // Store schedule times locally for display in the UI
        settingsRepository.setGhostwriterSchedule(
            morningHour = morning?.first ?: 7,
            morningMinute = morning?.second ?: 0,
            noonHour = noon?.first ?: 12,
            noonMinute = noon?.second ?: 0,
            eveningHour = evening?.first ?: 18,
            eveningMinute = evening?.second ?: 0,
            timezone = config.timezone
        )

        // Save the server's updated_at timestamp
        config.updatedAt?.let { settingsRepository.setConfigUpdatedAt(it) }

        Log.i(TAG, "Applied server config: schedule times synced, timezone=${config.timezone}")
    }

    /**
     * Parse "HH:mm" time string into hour and minute.
     */
    private fun parseTime(timeString: String?): Pair<Int, Int>? {
        if (timeString == null) return null
        val parts = timeString.split(":")
        if (parts.size != 2) return null
        val hour = parts[0].toIntOrNull() ?: return null
        val minute = parts[1].toIntOrNull() ?: return null
        return Pair(hour, minute)
    }

    /**
     * Push local configuration to the server.
     */
    private suspend fun pushLocalConfig(localUpdatedAt: String) {
        val schedule = settingsRepository.getGhostwriterSchedule()
        val result = ghostwriterRepository.updateConfig(
            timezone = schedule?.timezone,
            scheduleMorning = schedule?.let { String.format("%02d:%02d", it.morningHour, it.morningMinute) },
            scheduleNoon = schedule?.let { String.format("%02d:%02d", it.noonHour, it.noonMinute) },
            scheduleEvening = schedule?.let { String.format("%02d:%02d", it.eveningHour, it.eveningMinute) },
            clientUpdatedAt = localUpdatedAt
        )

        when (result) {
            is GhostwriterResult.Success -> {
                // Update local timestamp to match server
                settingsRepository.setConfigUpdatedAt(result.data.updatedAt)
                Log.i(TAG, "Pushed local config to server")
            }
            is GhostwriterResult.Error -> {
                if (result.code == 409) {
                    // Conflict - server was modified by another client
                    // Re-fetch and apply server config (server wins in conflict)
                    Log.w(TAG, "Conflict detected, re-fetching server config")
                    val refetchResult = ghostwriterRepository.getConfig()
                    if (refetchResult is GhostwriterResult.Success) {
                        applyServerConfig(refetchResult.data)
                    }
                } else {
                    Log.e(TAG, "Failed to push config: ${result.message}")
                }
            }
            is GhostwriterResult.NotConfigured -> {
                Log.d(TAG, "Ghostwriter not configured")
            }
        }
    }

    /**
     * Push a specific setting change to the server immediately.
     * Called when user changes a synced setting.
     */
    suspend fun pushMinWordCount(count: Int) {
        // min_word_count is no longer part of the server config schema;
        // it's only stored locally now.
        Log.d(TAG, "Min word count set locally: $count")
    }

    /**
     * Parse ISO 8601 timestamp to milliseconds.
     */
    private fun parseTimestamp(timestamp: String): Long {
        return try {
            val formats = listOf(
                "yyyy-MM-dd'T'HH:mm:ss.SSSSSS",
                "yyyy-MM-dd'T'HH:mm:ss.SSS",
                "yyyy-MM-dd'T'HH:mm:ss"
            )
            for (pattern in formats) {
                try {
                    val sdf = SimpleDateFormat(pattern, Locale.US)
                    sdf.timeZone = TimeZone.getTimeZone("UTC")
                    return sdf.parse(timestamp)?.time ?: 0L
                } catch (e: Exception) {
                    continue
                }
            }
            0L
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse timestamp: $timestamp", e)
            0L
        }
    }
}
