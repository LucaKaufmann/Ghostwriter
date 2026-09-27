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
import com.codable.epilogue.R
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.SettingsRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.CancellationException

/**
 * WorkManager worker that performs bi-directional feed sync with Ghostwriter.
 * Core sync logic is implemented in shared KMP FeedSyncV2UseCase.
 */
@HiltWorker
class FeedSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val feedSyncUseCase: FeedSyncV2UseCase,
    private val feedV2Store: AndroidFeedV2Store,
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

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting feed sync with Ghostwriter (attempt ${runAttemptCount})")

        try {
            setForeground(createForegroundInfo())
        } catch (e: IllegalStateException) {
            Log.w(TAG, "Could not start foreground service (app in background), continuing anyway")
        }

        return try {
            when (val outcome = feedSyncUseCase.sync().also { feedV2Store.recordOutcome(it) }) {
                is FeedSyncV2Outcome.Complete -> {
                    settingsRepository.setLastFeedSyncTime(System.currentTimeMillis())
                    Log.i(
                        TAG,
                        "Feed sync completed: applied=${outcome.applied}, pulled=${outcome.pulled}"
                    )
                    Result.success()
                }

                is FeedSyncV2Outcome.NotConfigured -> {
                    Log.i(TAG, "Ghostwriter not configured, skipping sync")
                    Result.success()
                }

                is FeedSyncV2Outcome.Partial -> {
                    Log.w(TAG, "Feed sync partial: phase=${outcome.phase}, pending=${outcome.pending}, conflicts=${outcome.conflicts}, rejected=${outcome.rejected}")
                    if (outcome.phase in setOf("push", "pull", "invalid_response")) retryOrFail()
                    else Result.success()
                }

                is FeedSyncV2Outcome.Failed -> {
                    Log.e(TAG, "Feed sync failed: ${outcome.message}")
                    retryOrFail()
                }
                FeedSyncV2Outcome.ServerChanged, FeedSyncV2Outcome.ServerUpgradeRequired -> {
                    Log.w(TAG, "Feed sync requires attention: $outcome")
                    Result.success()
                }
            }
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            Log.e(TAG, "Error syncing feeds", e)
            retryOrFail()
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
