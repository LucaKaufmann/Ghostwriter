package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.ClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigUpdateRequest

class ConfigSyncUseCase(
    private val settings: SettingsPort,
    private val ghostwriter: GhostwriterSyncPort
) {
    suspend fun syncConfig(): Boolean {
        if (!settings.isGhostwriterConfigured()) return false

        return when (val serverResult = ghostwriter.getConfig()) {
            is SyncPortResult.Success -> {
                val serverConfig = serverResult.data
                val localUpdatedAt = settings.getConfigUpdatedAt()

                if (localUpdatedAt == null) {
                    applyServerConfig(serverConfig)
                    return true
                }

                val serverUpdatedAt = serverConfig.updatedAt
                if (serverUpdatedAt == null) {
                    applyServerConfig(serverConfig)
                    return true
                }

                val serverTime = parseIso8601ToEpochMillis(serverUpdatedAt) ?: 0L
                val localTime = parseIso8601ToEpochMillis(localUpdatedAt) ?: 0L

                when {
                    serverTime > localTime -> applyServerConfig(serverConfig)
                    localTime > serverTime -> pushLocalConfig(localUpdatedAt)
                }

                true
            }
            is SyncPortResult.Error,
            is SyncPortResult.NotConfigured -> false
        }
    }

    suspend fun applyPreFetchedConfig(config: ClientConfigResponse): Boolean {
        val localUpdatedAt = settings.getConfigUpdatedAt()

        if (localUpdatedAt == null) {
            applyServerConfig(config)
            return true
        }

        val serverUpdatedAt = config.updatedAt
        if (serverUpdatedAt == null) {
            applyServerConfig(config)
            return true
        }

        val serverTime = parseIso8601ToEpochMillis(serverUpdatedAt) ?: 0L
        val localTime = parseIso8601ToEpochMillis(localUpdatedAt) ?: 0L

        if (serverTime >= localTime) {
            applyServerConfig(config)
        }

        return true
    }

    suspend fun pushMinWordCount(count: Int): Boolean {
        if (!settings.isGhostwriterConfigured()) return false

        val localUpdatedAt = settings.getConfigUpdatedAt()
        val result = ghostwriter.updateConfig(
            ClientConfigUpdateRequest(
                minWordCount = count,
                clientUpdatedAt = localUpdatedAt
            )
        )

        return when (result) {
            is SyncPortResult.Success -> {
                settings.setConfigUpdatedAt(result.data.updatedAt)
                true
            }
            is SyncPortResult.Error -> {
                if (result.code == 409) {
                    when (val refetch = ghostwriter.getConfig()) {
                        is SyncPortResult.Success -> applyServerConfig(refetch.data)
                        else -> Unit
                    }
                }
                false
            }
            is SyncPortResult.NotConfigured -> false
        }
    }

    private suspend fun applyServerConfig(config: ClientConfigResponse) {
        val morning = resolveTime(
            hour = config.morningHour,
            minute = config.morningMinute,
            legacyTime = config.scheduleMorning,
            defaultHour = 7,
            defaultMinute = 0
        )
        val noon = resolveTime(
            hour = config.noonHour,
            minute = config.noonMinute,
            legacyTime = config.scheduleNoon,
            defaultHour = 12,
            defaultMinute = 0
        )
        val evening = resolveTime(
            hour = config.eveningHour,
            minute = config.eveningMinute,
            legacyTime = config.scheduleEvening,
            defaultHour = 18,
            defaultMinute = 0
        )

        settings.setGhostwriterSchedule(
            GhostwriterScheduleSnapshot(
                morningHour = morning.first,
                morningMinute = morning.second,
                noonHour = noon.first,
                noonMinute = noon.second,
                eveningHour = evening.first,
                eveningMinute = evening.second,
                timezone = config.timezone
            )
        )

        config.minWordCount?.let { settings.setMinWordCount(it) }
        settings.setConfigUpdatedAt(config.updatedAt)
    }

    private suspend fun pushLocalConfig(localUpdatedAt: String) {
        val schedule = settings.getGhostwriterSchedule()
        val minWordCount = settings.getMinWordCount()

        val result = ghostwriter.updateConfig(
            ClientConfigUpdateRequest(
                minWordCount = minWordCount,
                morningHour = schedule?.morningHour,
                morningMinute = schedule?.morningMinute,
                noonHour = schedule?.noonHour,
                noonMinute = schedule?.noonMinute,
                eveningHour = schedule?.eveningHour,
                eveningMinute = schedule?.eveningMinute,
                timezone = schedule?.timezone,
                scheduleMorning = schedule?.let { formatTime(it.morningHour, it.morningMinute) },
                scheduleNoon = schedule?.let { formatTime(it.noonHour, it.noonMinute) },
                scheduleEvening = schedule?.let { formatTime(it.eveningHour, it.eveningMinute) },
                clientUpdatedAt = localUpdatedAt
            )
        )

        when (result) {
            is SyncPortResult.Success -> settings.setConfigUpdatedAt(result.data.updatedAt)
            is SyncPortResult.Error -> {
                if (result.code == 409) {
                    when (val refetch = ghostwriter.getConfig()) {
                        is SyncPortResult.Success -> applyServerConfig(refetch.data)
                        else -> Unit
                    }
                }
            }
            is SyncPortResult.NotConfigured -> Unit
        }
    }

    private fun parseTime(timeString: String?): Pair<Int, Int>? {
        if (timeString == null) return null
        val parts = timeString.split(":")
        if (parts.size != 2) return null
        val hour = parts[0].toIntOrNull() ?: return null
        val minute = parts[1].toIntOrNull() ?: return null
        return hour to minute
    }

    private fun resolveTime(
        hour: Int?,
        minute: Int?,
        legacyTime: String?,
        defaultHour: Int,
        defaultMinute: Int
    ): Pair<Int, Int> {
        if (hour != null && minute != null) {
            return hour to minute
        }
        return parseTime(legacyTime) ?: (defaultHour to defaultMinute)
    }

    private fun formatTime(hour: Int, minute: Int): String {
        return "${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}"
    }
}
