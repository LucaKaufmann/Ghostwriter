package com.example.epilogue.data.repository

import android.content.Context
import android.util.Log
import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.remote.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.data.remote.ghostwriter.SyncResponse
import com.example.epilogue.data.remote.ghostwriter.ClientStatusResponse
import com.example.epilogue.data.remote.ghostwriter.DigestArticlesResponse
import com.example.epilogue.data.remote.ghostwriter.DigestResponse
import com.example.epilogue.data.remote.ghostwriter.DigestStatusResponse
import com.example.epilogue.data.remote.ghostwriter.DigestTriggerRequest
import com.example.epilogue.data.remote.ghostwriter.DigestTriggerResponse
import com.example.epilogue.data.remote.ghostwriter.FeedChangesResponse
import com.example.epilogue.data.remote.ghostwriter.FeedSyncRequest
import com.example.epilogue.data.remote.ghostwriter.FeedSyncResponse
import com.example.epilogue.data.remote.ghostwriter.GhostwriterApi
import com.example.epilogue.data.remote.ghostwriter.HeartbeatResponse
import com.example.epilogue.data.remote.ghostwriter.HealthResponse
import com.example.epilogue.data.remote.ghostwriter.ScheduleResponse
import com.example.epilogue.data.remote.ghostwriter.ScheduleUpdateRequest
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import com.example.epilogue.di.GhostwriterApiFactory
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for interacting with the Ghostwriter backend service.
 *
 * Handles:
 * - Feed synchronization
 * - Digest triggering and status polling
 * - EPUB downloads
 * - Health checks
 */
@Singleton
class GhostwriterRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository,
    private val apiFactory: GhostwriterApiFactory
) {
    companion object {
        private const val TAG = "GhostwriterRepository"
    }

    /**
     * Result wrapper for Ghostwriter operations.
     */
    sealed class GhostwriterResult<out T> {
        data class Success<T>(val data: T) : GhostwriterResult<T>()
        data class Error(val message: String, val code: Int? = null) : GhostwriterResult<Nothing>()
        data object NotConfigured : GhostwriterResult<Nothing>()
    }

    /**
     * Get the API instance if Ghostwriter is configured.
     */
    private fun getApi(): GhostwriterApi? {
        val url = settingsRepository.getGhostwriterUrl()
        if (url.isNullOrBlank() || !settingsRepository.isGhostwriterEnabled()) {
            return null
        }
        return apiFactory.create(url)
    }

    /**
     * Get the authorization header value.
     */
    private fun getAuthHeader(): String? {
        val apiKey = settingsRepository.getGhostwriterApiKey()
        return if (!apiKey.isNullOrBlank()) "Bearer $apiKey" else null
    }

    /**
     * Check if Ghostwriter is configured and enabled.
     */
    fun isConfigured(): Boolean {
        return settingsRepository.isGhostwriterConfigured()
    }

    /**
     * Check the health of the Ghostwriter server.
     */
    suspend fun checkHealth(): GhostwriterResult<HealthResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getHealth()
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Health check failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Health check failed", e)
            GhostwriterResult.Error("Connection failed: ${e.message}")
        }
    }

    /**
     * Sync local feeds to the Ghostwriter backend.
     * This performs a full sync - feeds not in the list will be deactivated on the server.
     */
    suspend fun syncFeeds(feeds: List<Feed>): GhostwriterResult<FeedSyncResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            // Filter out synthetic feeds (wallabag, newsletters) - these are server-side integrations
            val realFeeds = feeds.filter { !it.url.startsWith("synthetic://") }

            val syncRequests = realFeeds.map { feed ->
                FeedSyncRequest(
                    url = feed.url,
                    title = feed.name,
                    isActive = feed.isEnabled,
                    mode = when (feed.mode) {
                        ProcessingMode.BRIEFING -> "summarize"
                        ProcessingMode.FIDELITY -> "raw"
                    },
                    maxArticles = if (feed.maxArticles > 0) feed.maxArticles else 10
                )
            }

            val response = api.syncFeeds(getAuthHeader(), syncRequests)
            if (response.isSuccessful && response.body() != null) {
                Log.i(TAG, "Synced ${response.body()!!.synced} feeds to Ghostwriter")
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Feed sync failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Feed sync failed", e)
            GhostwriterResult.Error("Sync failed: ${e.message}")
        }
    }

    /**
     * Get feed changes from the Ghostwriter backend for incremental sync.
     *
     * @param since Timestamp in milliseconds. If null, returns all feeds (initial sync).
     * @return Feed changes including updated feeds and tombstones for deleted feeds.
     */
    suspend fun getFeedChanges(since: Long?): GhostwriterResult<FeedChangesResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            // Convert timestamp to ISO 8601 format for the API
            val sinceStr = since?.let {
                val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
                sdf.timeZone = TimeZone.getTimeZone("UTC")
                sdf.format(java.util.Date(it))
            }

            val response = api.getFeedChanges(getAuthHeader(), sinceStr)
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                Log.i(TAG, "Got feed changes: ${body.feeds.size} feeds, ${body.tombstones.size} tombstones")
                GhostwriterResult.Success(body)
            } else {
                GhostwriterResult.Error(
                    message = "Get feed changes failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get feed changes failed", e)
            GhostwriterResult.Error("Get feed changes failed: ${e.message}")
        }
    }

    /**
     * Trigger a digest generation on the backend.
     *
     * @param period The time period: "morning", "noon", "evening", or "manual"
     * @return The digest ID if successful, or an error
     */
    suspend fun triggerDigest(period: String = "manual"): GhostwriterResult<DigestTriggerResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = DigestTriggerRequest(period = period)
            val response = api.triggerDigest(getAuthHeader(), request)

            if (response.isSuccessful && response.body() != null) {
                Log.i(TAG, "Triggered digest generation: ${response.body()!!.id}")
                GhostwriterResult.Success(response.body()!!)
            } else if (response.code() == 409) {
                GhostwriterResult.Error(
                    message = "A digest is already being generated",
                    code = 409
                )
            } else {
                GhostwriterResult.Error(
                    message = "Trigger failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Trigger digest failed", e)
            GhostwriterResult.Error("Trigger failed: ${e.message}")
        }
    }

    /**
     * Get the status of a running digest job.
     */
    suspend fun getDigestStatus(digestId: String): GhostwriterResult<DigestStatusResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getDigestStatus(getAuthHeader(), digestId)

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Status check failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get digest status failed", e)
            GhostwriterResult.Error("Status check failed: ${e.message}")
        }
    }

    /**
     * Get all articles for a digest with their content.
     * Used for syncing article content to display in-app.
     */
    suspend fun getDigestArticles(digestId: String): GhostwriterResult<DigestArticlesResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getDigestArticles(getAuthHeader(), digestId)

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else if (response.code() == 404) {
                GhostwriterResult.Error(
                    message = "Digest not found",
                    code = 404
                )
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get articles: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get digest articles failed", e)
            GhostwriterResult.Error("Failed to get articles: ${e.message}")
        }
    }

    /**
     * Get the most recent completed digest.
     */
    suspend fun getLatestDigest(): GhostwriterResult<DigestResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getLatestDigest(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else if (response.code() == 404) {
                GhostwriterResult.Error(
                    message = "No completed digests found",
                    code = 404
                )
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get latest digest: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get latest digest failed", e)
            GhostwriterResult.Error("Failed to get latest digest: ${e.message}")
        }
    }

    /**
     * List all available digests.
     */
    suspend fun listDigests(): GhostwriterResult<List<DigestResponse>> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listDigests(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to list digests: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "List digests failed", e)
            GhostwriterResult.Error("Failed to list digests: ${e.message}")
        }
    }

    /**
     * Download a digest EPUB file from the backend.
     *
     * @param filename The EPUB filename (e.g., "2024-01-20_manual.epub")
     * @return The local file path if successful
     */
    suspend fun downloadDigest(filename: String): GhostwriterResult<File> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.downloadDigest(getAuthHeader(), filename)

            if (response.isSuccessful && response.body() != null) {
                // Save to the app's documents directory
                val documentsDir = File(context.getExternalFilesDir(null), "Epilogue")
                if (!documentsDir.exists()) {
                    documentsDir.mkdirs()
                }

                val outputFile = File(documentsDir, filename)
                response.body()!!.byteStream().use { input ->
                    outputFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }

                Log.i(TAG, "Downloaded digest to: ${outputFile.absolutePath}")
                GhostwriterResult.Success(outputFile)
            } else {
                GhostwriterResult.Error(
                    message = "Download failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Download digest failed", e)
            GhostwriterResult.Error("Download failed: ${e.message}")
        }
    }

    /**
     * Delete a feed on the backend by URL.
     *
     * @param feedUrl The URL of the feed to delete
     * @return Success if deleted, Error otherwise
     */
    suspend fun deleteFeedByUrl(feedUrl: String): GhostwriterResult<Unit> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            // URL-encode the feed URL for the path
            val encodedUrl = java.net.URLEncoder.encode(feedUrl, "UTF-8")
            val response = api.deleteFeedByUrl(getAuthHeader(), encodedUrl)

            if (response.isSuccessful) {
                Log.i(TAG, "Deleted feed: $feedUrl")
                GhostwriterResult.Success(Unit)
            } else if (response.code() == 404) {
                // Feed doesn't exist on backend - treat as success
                Log.w(TAG, "Feed not found on backend: $feedUrl")
                GhostwriterResult.Success(Unit)
            } else {
                GhostwriterResult.Error(
                    message = "Delete failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Delete feed failed", e)
            GhostwriterResult.Error("Delete failed: ${e.message}")
        }
    }

    /**
     * Get all schedule configurations.
     */
    suspend fun getSchedules(): GhostwriterResult<List<ScheduleResponse>> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listSchedules(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get schedules: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get schedules failed", e)
            GhostwriterResult.Error("Failed to get schedules: ${e.message}")
        }
    }

    /**
     * Update a schedule configuration.
     *
     * @param period The period to update (morning, noon, evening)
     * @param enabled Whether the schedule should be enabled
     * @param hour Optional hour in 24h format
     * @param minute Optional minute
     */
    suspend fun updateSchedule(
        period: String,
        enabled: Boolean? = null,
        hour: Int? = null,
        minute: Int? = null
    ): GhostwriterResult<ScheduleResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = ScheduleUpdateRequest(
                enabled = enabled,
                hour = hour,
                minute = minute
            )
            val response = api.updateSchedule(getAuthHeader(), period.lowercase(), request)

            if (response.isSuccessful && response.body() != null) {
                Log.i(TAG, "Updated schedule for $period: enabled=$enabled")
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to update schedule: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Update schedule failed", e)
            GhostwriterResult.Error("Failed to update schedule: ${e.message}")
        }
    }

    /**
     * Send a heartbeat to indicate the app is active.
     * This prevents auto-disable of schedules due to inactivity.
     */
    suspend fun sendHeartbeat(): GhostwriterResult<HeartbeatResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.sendHeartbeat(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                Log.d(TAG, "Heartbeat sent successfully")
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Heartbeat failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Heartbeat failed", e)
            GhostwriterResult.Error("Heartbeat failed: ${e.message}")
        }
    }

    /**
     * Perform a combined sync that returns config, feeds, digests, and schedules
     * in a single API call.
     *
     * @param feedSince Timestamp in milliseconds for incremental feed sync. Null for initial sync.
     * @param knownDigestIds List of digest IDs the client already has, to exclude from response.
     */
    suspend fun performSync(feedSince: Long?, knownDigestIds: List<String>): GhostwriterResult<SyncResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val sinceStr = feedSince?.let {
                val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
                sdf.timeZone = TimeZone.getTimeZone("UTC")
                sdf.format(java.util.Date(it))
            }

            val digestIdsStr = if (knownDigestIds.isNotEmpty()) {
                knownDigestIds.joinToString(",")
            } else null

            val response = api.performSync(getAuthHeader(), sinceStr, digestIdsStr)
            if (response.isSuccessful && response.body() != null) {
                Log.i(TAG, "Combined sync successful")
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Combined sync failed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Combined sync failed", e)
            GhostwriterResult.Error("Combined sync failed: ${e.message}")
        }
    }

    /**
     * Get client status including activity tracking info.
     */
    suspend fun getClientStatus(): GhostwriterResult<ClientStatusResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getClientStatus(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get client status: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get client status failed", e)
            GhostwriterResult.Error("Failed to get client status: ${e.message}")
        }
    }

    /**
     * Get the shared client configuration from the server.
     * Used for syncing settings across devices on app startup.
     */
    suspend fun getConfig(): GhostwriterResult<ClientConfigResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getConfig(getAuthHeader())

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get config: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get config failed", e)
            GhostwriterResult.Error("Failed to get config: ${e.message}")
        }
    }

    /**
     * Update the shared client configuration on the server.
     *
     * @param minWordCount Minimum article word count (null to not update)
     * @param morningHour Morning schedule hour (24h)
     * @param morningMinute Morning schedule minute
     * @param noonHour Noon schedule hour (24h)
     * @param noonMinute Noon schedule minute
     * @param eveningHour Evening schedule hour (24h)
     * @param eveningMinute Evening schedule minute
     * @param timezone IANA timezone (null to not update)
     * @param scheduleMorning Legacy morning schedule time as "HH:mm" for backwards compatibility
     * @param scheduleNoon Legacy noon schedule time as "HH:mm" for backwards compatibility
     * @param scheduleEvening Legacy evening schedule time as "HH:mm" for backwards compatibility
     * @param clientUpdatedAt Client's last known server timestamp for conflict detection
     */
    suspend fun updateConfig(
        minWordCount: Int? = null,
        morningHour: Int? = null,
        morningMinute: Int? = null,
        noonHour: Int? = null,
        noonMinute: Int? = null,
        eveningHour: Int? = null,
        eveningMinute: Int? = null,
        timezone: String? = null,
        scheduleMorning: String? = null,
        scheduleNoon: String? = null,
        scheduleEvening: String? = null,
        clientUpdatedAt: String? = null
    ): GhostwriterResult<ClientConfigResponse> = withContext(Dispatchers.IO) {
        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = ClientConfigUpdateRequest(
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
                clientUpdatedAt = clientUpdatedAt
            )
            val response = api.updateConfig(getAuthHeader(), request)

            if (response.isSuccessful && response.body() != null) {
                Log.i(TAG, "Updated config on server")
                GhostwriterResult.Success(response.body()!!)
            } else if (response.code() == 409) {
                GhostwriterResult.Error(
                    message = "Config was modified by another device",
                    code = 409
                )
            } else {
                GhostwriterResult.Error(
                    message = "Failed to update config: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Update config failed", e)
            GhostwriterResult.Error("Failed to update config: ${e.message}")
        }
    }
}
