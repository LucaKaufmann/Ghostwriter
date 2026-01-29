package com.example.epilogue.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import com.example.epilogue.R
import com.example.epilogue.data.local.FeedEntity
import com.example.epilogue.data.remote.ghostwriter.FeedResponse
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * WorkManager worker that performs bi-directional feed sync with Ghostwriter.
 *
 * Sync flow:
 * 1. PUSH: Sync local feeds to server (existing syncFeeds API)
 * 2. PULL: Get changes from server (new getFeedChanges API)
 * 3. Apply server feeds locally (upsert)
 * 4. Apply tombstones (delete locally)
 * 5. Clear locallyModified flags
 * 6. Update lastFeedSyncTimestamp
 */
@HiltWorker
class FeedSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val ghostwriterRepository: GhostwriterRepository,
    private val feedRepository: FeedRepository,
    private val settingsRepository: SettingsRepository
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "FeedSyncWorker"
        const val WORK_NAME_PERIODIC = "feed_sync_periodic"
        const val WORK_NAME_IMMEDIATE = "feed_sync_immediate"

        const val NOTIFICATION_CHANNEL_ID = "feed_sync"
        const val NOTIFICATION_ID = 1003

        const val MAX_RETRY_ATTEMPTS = 3
    }

    private val dateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting feed sync with Ghostwriter (attempt ${runAttemptCount})")

        // Check if Ghostwriter is configured
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, skipping sync")
            return Result.success()
        }

        try {
            setForeground(createForegroundInfo())
        } catch (e: IllegalStateException) {
            Log.w(TAG, "Could not start foreground service (app in background), continuing anyway")
        }

        return try {
            // Step 1: PUSH - Sync local feeds to server
            val pushResult = pushLocalFeeds()
            if (!pushResult) {
                Log.w(TAG, "Push phase failed, continuing with pull")
            }

            // Step 2: PULL - Get changes from server
            val lastSyncTime = settingsRepository.getLastFeedSyncTime()
            val sinceTimestamp = if (lastSyncTime > 0) lastSyncTime else null

            Log.i(TAG, "Pulling feed changes since: ${sinceTimestamp ?: "initial sync"}")

            val changesResult = ghostwriterRepository.getFeedChanges(sinceTimestamp)

            when (changesResult) {
                is GhostwriterResult.Success -> {
                    val changes = changesResult.data

                    // Step 3: Apply server feeds locally
                    val serverFeeds = changes.feeds.map { response ->
                        convertResponseToFeed(response)
                    }

                    if (serverFeeds.isNotEmpty()) {
                        Log.i(TAG, "Applying ${serverFeeds.size} feeds from server")
                        feedRepository.upsertAll(serverFeeds)
                    }

                    // Step 4: Apply tombstones (delete locally)
                    val tombstoneUrls = changes.tombstones.map { it.url }
                    if (tombstoneUrls.isNotEmpty()) {
                        Log.i(TAG, "Applying ${tombstoneUrls.size} tombstones (deleting local feeds)")
                        feedRepository.deleteByUrls(tombstoneUrls)
                    }

                    // Step 5: Clear locallyModified flags
                    feedRepository.clearAllLocallyModified()

                    // Step 6: Update lastFeedSyncTimestamp
                    val serverTimestamp = parseServerTimestamp(changes.serverTimestamp)
                    settingsRepository.setLastFeedSyncTime(serverTimestamp)

                    Log.i(TAG, "Feed sync completed: ${serverFeeds.size} feeds updated, ${tombstoneUrls.size} deleted")
                    Result.success()
                }
                is GhostwriterResult.Error -> {
                    Log.e(TAG, "Failed to get feed changes: ${changesResult.message}")
                    retryOrFail()
                }
                is GhostwriterResult.NotConfigured -> {
                    Log.i(TAG, "Ghostwriter not configured")
                    Result.success()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error syncing feeds", e)
            retryOrFail()
        }
    }

    /**
     * Push local feeds to the server.
     * Returns true if successful.
     */
    private suspend fun pushLocalFeeds(): Boolean {
        val localFeeds = feedRepository.getAllFeedsList()

        if (localFeeds.isEmpty()) {
            Log.i(TAG, "No local feeds to push")
            return true
        }

        val result = ghostwriterRepository.syncFeeds(localFeeds)
        return when (result) {
            is GhostwriterResult.Success -> {
                Log.i(TAG, "Pushed ${result.data.synced} feeds to server")
                true
            }
            is GhostwriterResult.Error -> {
                Log.e(TAG, "Failed to push feeds: ${result.message}")
                false
            }
            is GhostwriterResult.NotConfigured -> {
                Log.w(TAG, "Ghostwriter not configured during push")
                false
            }
        }
    }

    /**
     * Convert a FeedResponse from the API to a Feed domain model.
     */
    private fun convertResponseToFeed(response: FeedResponse): Feed {
        val mode = when (response.mode) {
            "summarize" -> ProcessingMode.BRIEFING
            else -> ProcessingMode.FIDELITY
        }

        val serverUpdatedAt = try {
            dateFormat.parse(response.updatedAt)?.time ?: System.currentTimeMillis()
        } catch (e: Exception) {
            System.currentTimeMillis()
        }

        return Feed(
            url = response.url,
            name = response.title,
            mode = mode,
            maxArticles = response.maxArticles,
            serverUpdatedAt = serverUpdatedAt,
            locallyModified = false  // Server data is authoritative
        )
    }

    /**
     * Parse the server timestamp from ISO 8601 format to milliseconds.
     */
    private fun parseServerTimestamp(timestamp: String): Long {
        return try {
            dateFormat.parse(timestamp)?.time ?: System.currentTimeMillis()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse server timestamp: $timestamp", e)
            System.currentTimeMillis()
        }
    }

    private fun retryOrFail(): Result {
        return if (runAttemptCount < MAX_RETRY_ATTEMPTS) {
            Log.i(TAG, "Scheduling retry (attempt ${runAttemptCount + 1}/$MAX_RETRY_ATTEMPTS)")
            Result.retry()
        } else {
            Log.e(TAG, "Max retry attempts reached, failing")
            Result.failure()
        }
    }

    override suspend fun getForegroundInfo(): ForegroundInfo {
        return createForegroundInfo()
    }

    private fun createForegroundInfo(): ForegroundInfo {
        createNotificationChannel()

        val notification = NotificationCompat.Builder(applicationContext, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Syncing Feeds")
            .setContentText("Syncing feed configuration with Ghostwriter...")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            ForegroundInfo(NOTIFICATION_ID, notification)
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "Feed Sync",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shows progress while syncing feeds with Ghostwriter"
        }

        val notificationManager = applicationContext
            .getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.createNotificationChannel(channel)
    }
}
