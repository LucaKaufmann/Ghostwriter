package com.example.epilogue.data.repository

import android.content.Context
import android.content.pm.ApplicationInfo
import android.util.Log
import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.remote.ghostwriter.ClientConfigUpdateRequest
import com.example.epilogue.data.remote.ghostwriter.ClearSeenResponse
import com.example.epilogue.data.remote.ghostwriter.SyncResponse
import com.example.epilogue.data.remote.ghostwriter.AuthApiTokenCreateRequest
import com.example.epilogue.data.remote.ghostwriter.AuthApiTokenCreateResponse
import com.example.epilogue.data.remote.ghostwriter.AuthApiTokenResponse
import com.example.epilogue.data.remote.ghostwriter.ClientStatusResponse
import com.example.epilogue.data.remote.ghostwriter.DigestArticleSourceResponse
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
import com.example.epilogue.data.remote.ghostwriter.MediaFeedCreateRequest
import com.example.epilogue.data.remote.ghostwriter.MediaFeedResponse
import com.example.epilogue.data.remote.ghostwriter.MediaFeedUpdateRequest
import com.example.epilogue.data.remote.ghostwriter.MediaItemResponse
import com.example.epilogue.data.remote.ghostwriter.MediaItemSummaryResponse
import com.example.epilogue.data.remote.ghostwriter.MediaProcessingStatusResponse
import com.example.epilogue.data.remote.ghostwriter.MediaTriggerResponse
import com.example.epilogue.data.remote.ghostwriter.PreviewResponse
import com.example.epilogue.data.remote.ghostwriter.LogFileInfoResponse
import com.example.epilogue.data.remote.ghostwriter.ScheduleResponse
import com.example.epilogue.data.remote.ghostwriter.ScheduleUpdateRequest
import com.example.epilogue.data.remote.ghostwriter.SharedGhostwriterAdapter
import com.example.epilogue.data.remote.ghostwriter.StatusMessageResponse
import com.example.epilogue.data.remote.ghostwriter.YouTubeResolveRequest
import com.example.epilogue.data.remote.ghostwriter.YouTubeResolveResponse
import com.example.epilogue.shared.ghostwriter.GhostwriterApiException
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

    private var cachedSharedAdapter: SharedGhostwriterAdapter? = null
    private var cachedSharedBaseUrl: String? = null
    private var cachedSharedApiKey: String? = null

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

    private fun shouldUseSharedClient(): Boolean {
        val isDebuggable =
            (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
        return isDebuggable && settingsRepository.useSharedGhostwriterClient()
    }

    private fun getSharedAdapter(): SharedGhostwriterAdapter? {
        val url = settingsRepository.getGhostwriterUrl()
        if (url.isNullOrBlank() || !settingsRepository.isGhostwriterEnabled()) {
            return null
        }
        val apiKey = settingsRepository.getGhostwriterApiKey()

        if (cachedSharedAdapter != null &&
            cachedSharedBaseUrl == url &&
            cachedSharedApiKey == apiKey
        ) {
            return cachedSharedAdapter
        }

        cachedSharedAdapter?.close()
        cachedSharedAdapter = SharedGhostwriterAdapter.create(url, apiKey)
        cachedSharedBaseUrl = url
        cachedSharedApiKey = apiKey
        return cachedSharedAdapter
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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.checkHealth())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Health check failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Health check failed (shared)", e)
                GhostwriterResult.Error("Connection failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val realFeeds = feeds.filter { !it.url.startsWith("synthetic://") }
                val requests = realFeeds.map { feed ->
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
                GhostwriterResult.Success(shared.syncFeeds(requests))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Feed sync failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Feed sync failed (shared)", e)
                GhostwriterResult.Error("Sync failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val sinceStr = since?.toGhostwriterTimestamp()
                val response = shared.getFeedChanges(sinceStr)
                Log.i(TAG, "Got feed changes via shared client: ${response.feeds.size} feeds, ${response.tombstones.size} tombstones")
                GhostwriterResult.Success(response)
            } catch (e: GhostwriterApiException) {
                sharedApiError("Get feed changes failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get feed changes failed (shared)", e)
                GhostwriterResult.Error("Get feed changes failed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val sinceStr = since?.toGhostwriterTimestamp()

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.triggerDigest(period))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Trigger failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Trigger digest failed (shared)", e)
                GhostwriterResult.Error("Trigger failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getDigestStatus(digestId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Status check failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get digest status failed (shared)", e)
                GhostwriterResult.Error("Status check failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getDigestArticles(digestId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get articles (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get digest articles failed (shared)", e)
                GhostwriterResult.Error("Failed to get articles: ${e.message}")
            }
        }

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
     * Get raw/source HTML for a digest article.
     * Used for reader/source-mode parity with the web client.
     */
    suspend fun getDigestArticleSource(
        digestId: String,
        articleId: String
    ): GhostwriterResult<DigestArticleSourceResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getDigestArticleSource(digestId, articleId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get article source (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get digest article source failed (shared)", e)
                GhostwriterResult.Error("Failed to get article source: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getDigestArticleSource(getAuthHeader(), digestId, articleId)

            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else if (response.code() == 404) {
                GhostwriterResult.Error(
                    message = "Article not found",
                    code = 404
                )
            } else {
                GhostwriterResult.Error(
                    message = "Failed to get article source: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get digest article source failed", e)
            GhostwriterResult.Error("Failed to get article source: ${e.message}")
        }
    }

    /**
     * Get the most recent completed digest.
     */
    suspend fun getLatestDigest(): GhostwriterResult<DigestResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getLatestDigest())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get latest digest (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get latest digest failed (shared)", e)
                GhostwriterResult.Error("Failed to get latest digest: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.listDigests())
            } catch (e: GhostwriterApiException) {
                sharedApiError("List digests failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "List digests failed (shared)", e)
                GhostwriterResult.Error("Failed to list digests: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                shared.deleteFeedByUrl(feedUrl)
                Log.i(TAG, "Deleted feed via shared client: $feedUrl")
                GhostwriterResult.Success(Unit)
            } catch (e: GhostwriterApiException.NotFound) {
                // Feed doesn't exist on backend - treat as success
                Log.w(TAG, "Feed not found on backend via shared client: $feedUrl")
                GhostwriterResult.Success(Unit)
            } catch (e: GhostwriterApiException) {
                sharedApiError("Delete feed failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Delete feed failed (shared)", e)
                GhostwriterResult.Error("Delete failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getSchedules())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get schedules (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get schedules failed (shared)", e)
                GhostwriterResult.Error("Failed to get schedules: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val request = ScheduleUpdateRequest(
                    enabled = enabled,
                    hour = hour,
                    minute = minute
                )
                GhostwriterResult.Success(shared.updateSchedule(period.lowercase(), request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to update schedule (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Update schedule failed (shared)", e)
                GhostwriterResult.Error("Failed to update schedule: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.sendHeartbeat())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Heartbeat failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Heartbeat failed (shared)", e)
                GhostwriterResult.Error("Heartbeat failed: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val sinceStr = feedSince?.toGhostwriterTimestamp()
                val digestIdsStr = if (knownDigestIds.isNotEmpty()) knownDigestIds.joinToString(",") else null
                val response = shared.performSync(sinceStr, digestIdsStr)
                Log.i(TAG, "Combined sync successful via shared client")
                GhostwriterResult.Success(response)
            } catch (e: GhostwriterApiException) {
                sharedApiError("Combined sync failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Combined sync failed (shared)", e)
                GhostwriterResult.Error("Combined sync failed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val sinceStr = feedSince?.toGhostwriterTimestamp()

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getClientStatus())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get client status (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get client status failed (shared)", e)
                GhostwriterResult.Error("Failed to get client status: ${e.message}")
            }
        }

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
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getConfig())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to get config (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get config failed (shared)", e)
                GhostwriterResult.Error("Failed to get config: ${e.message}")
            }
        }

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
     * @param includePodcastsInDigest Include completed podcast transcripts in digest generation
     * @param includeYoutubeInDigest Include completed YouTube transcripts in digest generation
     * @param coverEnabled Enable AI cover generation
     * @param coverProvider Cover generation provider identifier
     * @param coverQuality Cover quality level
     * @param coverPrompt Additional cover generation prompt text
     * @param coverOverlayEnabled Enable deterministic metadata overlay on generated covers
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
        includePodcastsInDigest: Boolean? = null,
        includeYoutubeInDigest: Boolean? = null,
        coverEnabled: Boolean? = null,
        coverProvider: String? = null,
        coverQuality: String? = null,
        coverPrompt: String? = null,
        coverOverlayEnabled: Boolean? = null,
        clientUpdatedAt: String? = null
    ): GhostwriterResult<ClientConfigResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
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
                    includePodcastsInDigest = includePodcastsInDigest,
                    includeYoutubeInDigest = includeYoutubeInDigest,
                    coverEnabled = coverEnabled,
                    coverProvider = coverProvider,
                    coverQuality = coverQuality,
                    coverPrompt = coverPrompt,
                    coverOverlayEnabled = coverOverlayEnabled,
                    clientUpdatedAt = clientUpdatedAt
                )
                GhostwriterResult.Success(shared.updateConfig(request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Update config failed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Update config failed (shared)", e)
                GhostwriterResult.Error("Failed to update config: ${e.message}")
            }
        }

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
                includePodcastsInDigest = includePodcastsInDigest,
                includeYoutubeInDigest = includeYoutubeInDigest,
                coverEnabled = coverEnabled,
                coverProvider = coverProvider,
                coverQuality = coverQuality,
                coverPrompt = coverPrompt,
                coverOverlayEnabled = coverOverlayEnabled,
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

    /**
     * Preview Wallabag items without mutating read state.
     */
    suspend fun previewWallabag(): GhostwriterResult<PreviewResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.previewWallabag())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to preview Wallabag (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Preview Wallabag failed (shared)", e)
                GhostwriterResult.Error("Failed to preview Wallabag: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.previewWallabag(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to preview Wallabag: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Preview Wallabag failed", e)
            GhostwriterResult.Error("Failed to preview Wallabag: ${e.message}")
        }
    }

    /**
     * Preview newsletter items without mutating read state.
     */
    suspend fun previewNewsletters(): GhostwriterResult<PreviewResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.previewNewsletters())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to preview newsletters (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Preview newsletters failed (shared)", e)
                GhostwriterResult.Error("Failed to preview newsletters: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.previewNewsletters(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to preview newsletters: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Preview newsletters failed", e)
            GhostwriterResult.Error("Failed to preview newsletters: ${e.message}")
        }
    }

    /**
     * Clear seen markers for Wallabag synthetic feed.
     */
    suspend fun clearWallabagSeen(): GhostwriterResult<ClearSeenResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.clearWallabagSeen())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to clear Wallabag seen cache (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Clear Wallabag seen failed (shared)", e)
                GhostwriterResult.Error("Failed to clear Wallabag seen cache: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.clearWallabagSeen(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to clear Wallabag seen cache: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Clear Wallabag seen failed", e)
            GhostwriterResult.Error("Failed to clear Wallabag seen cache: ${e.message}")
        }
    }

    /**
     * Clear seen markers for newsletters synthetic feed.
     */
    suspend fun clearNewsletterSeen(): GhostwriterResult<ClearSeenResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.clearNewsletterSeen())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to clear newsletter seen cache (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Clear newsletter seen failed (shared)", e)
                GhostwriterResult.Error("Failed to clear newsletter seen cache: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.clearNewsletterSeen(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to clear newsletter seen cache: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Clear newsletter seen failed", e)
            GhostwriterResult.Error("Failed to clear newsletter seen cache: ${e.message}")
        }
    }

    private fun Long.toGhostwriterTimestamp(): String {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
        sdf.timeZone = TimeZone.getTimeZone("UTC")
        return sdf.format(java.util.Date(this))
    }

    private fun sharedApiError(prefix: String, e: GhostwriterApiException): GhostwriterResult.Error {
        return when (e) {
            is GhostwriterApiException.Conflict -> GhostwriterResult.Error("$prefix: conflict", 409)
            is GhostwriterApiException.Unauthorized -> GhostwriterResult.Error("$prefix: unauthorized", 401)
            is GhostwriterApiException.NotFound -> GhostwriterResult.Error("$prefix: not found", 404)
            is GhostwriterApiException.RateLimited -> GhostwriterResult.Error("$prefix: rate limited", 429)
            is GhostwriterApiException.HttpError -> GhostwriterResult.Error("$prefix: http ${e.statusCode}", e.statusCode)
        }
    }

    /**
     * List configured podcast feeds.
     */
    suspend fun getPodcastFeeds(): GhostwriterResult<List<MediaFeedResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getPodcastFeeds())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load podcast feeds (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get podcast feeds failed (shared)", e)
                GhostwriterResult.Error("Failed to load podcast feeds: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listPodcastFeeds(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load podcast feeds: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get podcast feeds failed", e)
            GhostwriterResult.Error("Failed to load podcast feeds: ${e.message}")
        }
    }

    /**
     * Create a podcast feed.
     */
    suspend fun createPodcastFeed(
        url: String,
        title: String,
        mode: String = "raw",
        maxItems: Int = 5,
        isActive: Boolean = true
    ): GhostwriterResult<MediaFeedResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val request = MediaFeedCreateRequest(
                    feedType = "podcast",
                    url = url,
                    title = title,
                    isActive = isActive,
                    mode = mode,
                    maxItems = maxItems
                )
                GhostwriterResult.Success(shared.createPodcastFeed(request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to create podcast feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Create podcast feed failed (shared)", e)
                GhostwriterResult.Error("Failed to create podcast feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = MediaFeedCreateRequest(
                feedType = "podcast",
                url = url,
                title = title,
                isActive = isActive,
                mode = mode,
                maxItems = maxItems
            )
            val response = api.createPodcastFeed(getAuthHeader(), request)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to create podcast feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Create podcast feed failed", e)
            GhostwriterResult.Error("Failed to create podcast feed: ${e.message}")
        }
    }

    /**
     * Update a podcast feed.
     */
    suspend fun updatePodcastFeed(
        feedId: String,
        title: String? = null,
        isActive: Boolean? = null,
        mode: String? = null,
        maxItems: Int? = null
    ): GhostwriterResult<MediaFeedResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val request = MediaFeedUpdateRequest(
                    title = title,
                    isActive = isActive,
                    mode = mode,
                    maxItems = maxItems
                )
                GhostwriterResult.Success(shared.updatePodcastFeed(feedId, request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to update podcast feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Update podcast feed failed (shared)", e)
                GhostwriterResult.Error("Failed to update podcast feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = MediaFeedUpdateRequest(
                title = title,
                isActive = isActive,
                mode = mode,
                maxItems = maxItems
            )
            val response = api.updatePodcastFeed(getAuthHeader(), feedId, request)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to update podcast feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Update podcast feed failed", e)
            GhostwriterResult.Error("Failed to update podcast feed: ${e.message}")
        }
    }

    /**
     * Delete a podcast feed.
     */
    suspend fun deletePodcastFeed(feedId: String): GhostwriterResult<StatusMessageResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.deletePodcastFeed(feedId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to delete podcast feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Delete podcast feed failed (shared)", e)
                GhostwriterResult.Error("Failed to delete podcast feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.deletePodcastFeed(getAuthHeader(), feedId)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to delete podcast feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Delete podcast feed failed", e)
            GhostwriterResult.Error("Failed to delete podcast feed: ${e.message}")
        }
    }

    /**
     * List configured YouTube feeds.
     */
    suspend fun getYouTubeFeeds(): GhostwriterResult<List<MediaFeedResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getYouTubeFeeds())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load YouTube feeds (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get YouTube feeds failed (shared)", e)
                GhostwriterResult.Error("Failed to load YouTube feeds: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listYouTubeFeeds(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load YouTube feeds: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get YouTube feeds failed", e)
            GhostwriterResult.Error("Failed to load YouTube feeds: ${e.message}")
        }
    }

    /**
     * Resolve a YouTube channel URL to RSS URL.
     */
    suspend fun resolveYouTubeFeed(url: String): GhostwriterResult<YouTubeResolveResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.resolveYouTubeFeed(url))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to resolve YouTube URL (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Resolve YouTube feed failed (shared)", e)
                GhostwriterResult.Error("Failed to resolve YouTube URL: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.resolveYouTubeFeed(getAuthHeader(), YouTubeResolveRequest(url))
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to resolve YouTube URL: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Resolve YouTube feed failed", e)
            GhostwriterResult.Error("Failed to resolve YouTube URL: ${e.message}")
        }
    }

    /**
     * Create a YouTube feed.
     */
    suspend fun createYouTubeFeed(
        url: String,
        resolvedFeedUrl: String? = null,
        title: String,
        mode: String = "raw",
        maxItems: Int = 5,
        isActive: Boolean = true
    ): GhostwriterResult<MediaFeedResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val request = MediaFeedCreateRequest(
                    feedType = "youtube",
                    url = url,
                    resolvedFeedUrl = resolvedFeedUrl,
                    title = title,
                    isActive = isActive,
                    mode = mode,
                    maxItems = maxItems
                )
                GhostwriterResult.Success(shared.createYouTubeFeed(request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to create YouTube feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Create YouTube feed failed (shared)", e)
                GhostwriterResult.Error("Failed to create YouTube feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = MediaFeedCreateRequest(
                feedType = "youtube",
                url = url,
                resolvedFeedUrl = resolvedFeedUrl,
                title = title,
                isActive = isActive,
                mode = mode,
                maxItems = maxItems
            )
            val response = api.createYouTubeFeed(getAuthHeader(), request)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to create YouTube feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Create YouTube feed failed", e)
            GhostwriterResult.Error("Failed to create YouTube feed: ${e.message}")
        }
    }

    /**
     * Update a YouTube feed.
     */
    suspend fun updateYouTubeFeed(
        feedId: String,
        title: String? = null,
        isActive: Boolean? = null,
        mode: String? = null,
        maxItems: Int? = null
    ): GhostwriterResult<MediaFeedResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                val request = MediaFeedUpdateRequest(
                    title = title,
                    isActive = isActive,
                    mode = mode,
                    maxItems = maxItems
                )
                GhostwriterResult.Success(shared.updateYouTubeFeed(feedId, request))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to update YouTube feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Update YouTube feed failed (shared)", e)
                GhostwriterResult.Error("Failed to update YouTube feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val request = MediaFeedUpdateRequest(
                title = title,
                isActive = isActive,
                mode = mode,
                maxItems = maxItems
            )
            val response = api.updateYouTubeFeed(getAuthHeader(), feedId, request)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to update YouTube feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Update YouTube feed failed", e)
            GhostwriterResult.Error("Failed to update YouTube feed: ${e.message}")
        }
    }

    /**
     * Delete a YouTube feed.
     */
    suspend fun deleteYouTubeFeed(feedId: String): GhostwriterResult<StatusMessageResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.deleteYouTubeFeed(feedId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to delete YouTube feed (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Delete YouTube feed failed (shared)", e)
                GhostwriterResult.Error("Failed to delete YouTube feed: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.deleteYouTubeFeed(getAuthHeader(), feedId)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to delete YouTube feed: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Delete YouTube feed failed", e)
            GhostwriterResult.Error("Failed to delete YouTube feed: ${e.message}")
        }
    }

    /**
     * List all podcast media items.
     */
    suspend fun getAllPodcastItems(): GhostwriterResult<List<MediaItemSummaryResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getAllPodcastItems())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load podcast items (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get podcast items failed (shared)", e)
                GhostwriterResult.Error("Failed to load podcast items: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listAllPodcastItems(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load podcast items: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get podcast items failed", e)
            GhostwriterResult.Error("Failed to load podcast items: ${e.message}")
        }
    }

    /**
     * List all YouTube media items.
     */
    suspend fun getAllYouTubeItems(): GhostwriterResult<List<MediaItemSummaryResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getAllYouTubeItems())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load YouTube items (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get YouTube items failed (shared)", e)
                GhostwriterResult.Error("Failed to load YouTube items: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listAllYouTubeItems(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load YouTube items: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get YouTube items failed", e)
            GhostwriterResult.Error("Failed to load YouTube items: ${e.message}")
        }
    }

    /**
     * Get full media item details with transcript body.
     */
    suspend fun getMediaItem(itemId: String): GhostwriterResult<MediaItemResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getMediaItem(itemId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load media item (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get media item failed (shared)", e)
                GhostwriterResult.Error("Failed to load media item: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getMediaItem(getAuthHeader(), itemId)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load media item: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get media item failed", e)
            GhostwriterResult.Error("Failed to load media item: ${e.message}")
        }
    }

    /**
     * Get aggregate media processing status.
     */
    suspend fun getMediaStatus(): GhostwriterResult<MediaProcessingStatusResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getMediaStatus())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to load media status (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get media status failed (shared)", e)
                GhostwriterResult.Error("Failed to load media status: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.getMediaStatus(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to load media status: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get media status failed", e)
            GhostwriterResult.Error("Failed to load media status: ${e.message}")
        }
    }

    /**
     * Trigger media processing pipeline.
     */
    suspend fun triggerMediaProcessing(): GhostwriterResult<MediaTriggerResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.triggerMediaProcessing())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to trigger media processing (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Trigger media processing failed (shared)", e)
                GhostwriterResult.Error("Failed to trigger media processing: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.triggerMediaProcessing(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to trigger media processing: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Trigger media processing failed", e)
            GhostwriterResult.Error("Failed to trigger media processing: ${e.message}")
        }
    }

    /**
     * List available server logs.
     */
    suspend fun getLogFiles(): GhostwriterResult<List<LogFileInfoResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.getLogFiles())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to list log files (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Get log files failed (shared)", e)
                GhostwriterResult.Error("Failed to list log files: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured

        try {
            val response = api.listLogFiles(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to list log files: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Get log files failed", e)
            GhostwriterResult.Error("Failed to list log files: ${e.message}")
        }
    }

    /**
     * List auth API tokens for current JWT-authenticated user.
     */
    suspend fun listAuthTokens(): GhostwriterResult<List<AuthApiTokenResponse>> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.listAuthTokens())
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to list auth tokens (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "List auth tokens failed (shared)", e)
                GhostwriterResult.Error("Failed to list auth tokens: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured
        try {
            val response = api.listAuthTokens(getAuthHeader())
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to list auth tokens: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "List auth tokens failed", e)
            GhostwriterResult.Error("Failed to list auth tokens: ${e.message}")
        }
    }

    /**
     * Create a new auth API token for current JWT-authenticated user.
     */
    suspend fun createAuthToken(name: String): GhostwriterResult<AuthApiTokenCreateResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.createAuthToken(name))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to create auth token (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Create auth token failed (shared)", e)
                GhostwriterResult.Error("Failed to create auth token: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured
        try {
            val response = api.createAuthToken(getAuthHeader(), AuthApiTokenCreateRequest(name))
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to create auth token: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Create auth token failed", e)
            GhostwriterResult.Error("Failed to create auth token: ${e.message}")
        }
    }

    /**
     * Revoke an existing auth API token.
     */
    suspend fun revokeAuthToken(tokenId: String): GhostwriterResult<StatusMessageResponse> = withContext(Dispatchers.IO) {
        if (shouldUseSharedClient()) {
            val shared = getSharedAdapter() ?: return@withContext GhostwriterResult.NotConfigured
            return@withContext try {
                GhostwriterResult.Success(shared.revokeAuthToken(tokenId))
            } catch (e: GhostwriterApiException) {
                sharedApiError("Failed to revoke auth token (shared)", e)
            } catch (e: Exception) {
                Log.e(TAG, "Revoke auth token failed (shared)", e)
                GhostwriterResult.Error("Failed to revoke auth token: ${e.message}")
            }
        }

        val api = getApi() ?: return@withContext GhostwriterResult.NotConfigured
        try {
            val response = api.revokeAuthToken(getAuthHeader(), tokenId)
            if (response.isSuccessful && response.body() != null) {
                GhostwriterResult.Success(response.body()!!)
            } else {
                GhostwriterResult.Error(
                    message = "Failed to revoke auth token: ${response.message()}",
                    code = response.code()
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Revoke auth token failed", e)
            GhostwriterResult.Error("Failed to revoke auth token: ${e.message}")
        }
    }
}
