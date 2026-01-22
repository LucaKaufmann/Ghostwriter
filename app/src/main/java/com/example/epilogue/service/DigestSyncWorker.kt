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
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * WorkManager worker that syncs digests from Ghostwriter backend.
 * Checks for new completed digests and downloads them to the device.
 */
@HiltWorker
class DigestSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val ghostwriterRepository: GhostwriterRepository,
    private val digestRepository: DigestRepository,
    private val settingsRepository: SettingsRepository,
    private val epubExporter: EpubExporter
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DigestSyncWorker"
        const val WORK_NAME = "digest_sync_work"
        const val WORK_NAME_IMMEDIATE = "digest_sync_immediate"

        const val NOTIFICATION_CHANNEL_ID = "digest_sync"
        const val NOTIFICATION_ID = 1002

        const val MAX_RETRY_ATTEMPTS = 3
    }

    private val dateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting digest sync from Ghostwriter (attempt ${runAttemptCount})")

        // Check if Ghostwriter is configured
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, skipping sync")
            return Result.success()
        }

        setForeground(createForegroundInfo())

        return try {
            // Get list of digests from Ghostwriter
            val digestsResult = ghostwriterRepository.listDigests()

            when (digestsResult) {
                is GhostwriterResult.Success -> {
                    val remoteDigests = digestsResult.data
                    val existingRemoteIds = digestRepository.getAllRemoteIds().toSet()

                    // Filter to only completed digests we don't have
                    val newDigests = remoteDigests.filter { digest ->
                        digest.status == "completed" &&
                        digest.id !in existingRemoteIds
                    }

                    Log.i(TAG, "Found ${newDigests.size} new digests to download")

                    var downloadedCount = 0
                    for (digest in newDigests) {
                        val downloadResult = ghostwriterRepository.downloadDigest(digest.filename)

                        when (downloadResult) {
                            is GhostwriterResult.Success -> {
                                val file = downloadResult.data
                                Log.i(TAG, "Downloaded: ${file.absolutePath}")

                                // Parse timestamp
                                val generatedAt = try {
                                    digest.completedAt?.let { dateFormat.parse(it)?.time }
                                        ?: System.currentTimeMillis()
                                } catch (e: Exception) {
                                    System.currentTimeMillis()
                                }

                                // Save to local database
                                digestRepository.saveRemoteDigest(
                                    remoteId = digest.id,
                                    epubFilePath = file.absolutePath,
                                    articleCount = digest.articleCount,
                                    generatedAt = generatedAt,
                                    period = digest.period
                                )

                                // Export to custom directory if configured
                                when (val exportResult = epubExporter.exportToCustomDirectory(file)) {
                                    is ExportResult.Success ->
                                        Log.i(TAG, "Exported to custom directory")
                                    is ExportResult.PermissionRevoked ->
                                        Log.w(TAG, "Custom export permission revoked")
                                    is ExportResult.Error ->
                                        Log.e(TAG, "Custom export failed: ${exportResult.message}")
                                    ExportResult.NotConfigured -> { /* No-op */ }
                                }

                                downloadedCount++
                            }
                            is GhostwriterResult.Error -> {
                                Log.e(TAG, "Failed to download ${digest.filename}: ${downloadResult.message}")
                            }
                            is GhostwriterResult.NotConfigured -> {
                                Log.e(TAG, "Ghostwriter not configured during download")
                            }
                        }
                    }

                    Log.i(TAG, "Downloaded $downloadedCount new digests")

                    // Update last sync time
                    settingsRepository.setLastDigestSyncTime(System.currentTimeMillis())

                    Result.success()
                }
                is GhostwriterResult.Error -> {
                    Log.e(TAG, "Failed to list digests: ${digestsResult.message}")
                    retryOrFail()
                }
                is GhostwriterResult.NotConfigured -> {
                    Log.i(TAG, "Ghostwriter not configured")
                    Result.success()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error syncing digests", e)
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
            .setContentTitle("Syncing Digests")
            .setContentText("Checking for new digests from Ghostwriter...")
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
            "Digest Sync",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shows progress while syncing digests from Ghostwriter"
        }

        val notificationManager = applicationContext
            .getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.createNotificationChannel(channel)
    }
}
