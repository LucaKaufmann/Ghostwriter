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
import com.example.epilogue.data.repository.ArticleRepository
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.domain.model.DigestPeriod
import com.example.epilogue.domain.model.TriggerType
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.io.IOException
import java.util.Date

/**
 * WorkManager worker that generates the daily EPUB digest.
 * Fetches articles from all configured feeds, processes them according to their mode,
 * and generates an EPUB file. Also saves the digest to history.
 */
@HiltWorker
class DailyDigestWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val articleRepository: ArticleRepository,
    private val feedRepository: FeedRepository,
    private val digestRepository: DigestRepository,
    private val epubGenerator: EpubGenerator,
    private val epubExporter: EpubExporter
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DailyDigestWorker"
        const val WORK_NAME = "daily_digest_work"

        // Input data keys
        const val KEY_FETCH_ALL = "fetch_all"  // If true, fetch all articles (not just new)
        const val KEY_IS_MANUAL = "is_manual"  // If true, triggered manually (not scheduled)
        const val KEY_PERIOD = "period"  // Period name (MORNING, NOON, EVENING) for scheduled digests

        // Notification constants for foreground service
        const val NOTIFICATION_CHANNEL_ID = "digest_generation"
        const val NOTIFICATION_ID = 1001

        // Retry configuration
        const val MAX_RETRY_ATTEMPTS = 3
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting daily digest generation (attempt ${runAttemptCount})")

        // Set foreground for long-running work
        setForeground(createForegroundInfo())

        return try {
            val fetchOnlyNew = !inputData.getBoolean(KEY_FETCH_ALL, false)
            val isManual = inputData.getBoolean(KEY_IS_MANUAL, false)
            val periodName = inputData.getString(KEY_PERIOD)
            val period = periodName?.let {
                try {
                    DigestPeriod.valueOf(it)
                } catch (e: IllegalArgumentException) {
                    null
                }
            }

            // Get all feeds for later reference
            val feeds = feedRepository.getAllFeedsList()

            // Fetch and process articles from all feeds
            val articles = articleRepository.fetchFromAllFeeds(onlyNew = fetchOnlyNew)

            if (articles.isEmpty()) {
                Log.i(TAG, "No articles to process")
                return Result.success()
            }

            Log.i(TAG, "Fetched ${articles.size} articles")

            // Generate EPUB with optional period for filename
            val result = epubGenerator.generate(articles, Date(), period)

            if (result != null) {
                Log.i(TAG, "Generated EPUB: ${result.file.absolutePath}")

                // Export to custom directory if configured
                when (val exportResult = epubExporter.exportToCustomDirectory(result.file)) {
                    is ExportResult.Success ->
                        Log.i(TAG, "Exported to custom directory")
                    is ExportResult.PermissionRevoked ->
                        Log.w(TAG, "Custom export permission revoked")
                    is ExportResult.Error ->
                        Log.e(TAG, "Custom export failed: ${exportResult.message}")
                    ExportResult.NotConfigured -> { /* No-op */ }
                }

                // Save to digest history
                val triggerType = if (isManual) TriggerType.MANUAL else TriggerType.SCHEDULED
                digestRepository.saveDigest(
                    articles = result.articles,
                    feeds = feeds,
                    epubFilePath = result.file.absolutePath,
                    triggerType = triggerType
                )
                Log.i(TAG, "Saved digest to history")

                Result.success()
            } else {
                Log.e(TAG, "Failed to generate EPUB")
                retryOrFail()
            }
        } catch (e: IOException) {
            // Network errors are retriable
            Log.e(TAG, "Network error generating digest", e)
            retryOrFail()
        } catch (e: Exception) {
            Log.e(TAG, "Error generating digest", e)
            Result.failure()
        }
    }

    /**
     * Returns Result.retry() if under max attempts, otherwise Result.failure()
     */
    private fun retryOrFail(): Result {
        return if (runAttemptCount < MAX_RETRY_ATTEMPTS) {
            Log.i(TAG, "Scheduling retry (attempt ${runAttemptCount + 1}/$MAX_RETRY_ATTEMPTS)")
            Result.retry()
        } else {
            Log.e(TAG, "Max retry attempts reached, failing")
            Result.failure()
        }
    }

    /**
     * Required for expedited work - provides notification for foreground service.
     */
    override suspend fun getForegroundInfo(): ForegroundInfo {
        return createForegroundInfo()
    }

    private fun createForegroundInfo(): ForegroundInfo {
        createNotificationChannel()

        val notification = NotificationCompat.Builder(applicationContext, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Generating Digest")
            .setContentText("Fetching articles and creating EPUB...")
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
            "Digest Generation",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shows progress while generating daily digest"
        }

        val notificationManager = applicationContext
            .getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.createNotificationChannel(channel)
    }
}
