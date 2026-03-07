package com.example.epilogue.service

import android.util.Log
import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.shared.ghostwriter.ClientConfigResponse as SharedClientConfigResponse
import com.example.epilogue.shared.ghostwriter.IntegrationStatus as SharedIntegrationStatus
import com.example.epilogue.shared.sync.ConfigSyncUseCase
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Android wrapper around shared KMP config sync logic.
 */
@Singleton
class ConfigSyncManager @Inject constructor(
    private val configSyncUseCase: ConfigSyncUseCase
) {
    companion object {
        private const val TAG = "ConfigSyncManager"
    }

    suspend fun syncConfig(): Boolean {
        return try {
            configSyncUseCase.syncConfig()
        } catch (e: Exception) {
            Log.e(TAG, "Failed syncing config", e)
            false
        }
    }

    suspend fun applyPreFetchedConfig(config: ClientConfigResponse): Boolean {
        return try {
            configSyncUseCase.applyPreFetchedConfig(config.toShared())
        } catch (e: Exception) {
            Log.e(TAG, "Failed to apply pre-fetched config", e)
            false
        }
    }

    suspend fun pushMinWordCount(count: Int) {
        try {
            configSyncUseCase.pushMinWordCount(count)
        } catch (e: Exception) {
            Log.e(TAG, "Failed syncing min_word_count", e)
        }
    }
}

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
    wallabag = wallabag?.let { SharedIntegrationStatus(enabled = it.enabled, label = it.label) },
    newsletters = newsletters?.let { SharedIntegrationStatus(enabled = it.enabled, label = it.label) }
)
