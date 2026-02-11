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
import com.example.epilogue.data.remote.ghostwriter.SyncDigest
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import java.io.File
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

        try {
            setForeground(createForegroundInfo())
        } catch (e: IllegalStateException) {
            Log.w(TAG, "Could not start foreground service (app in background), continuing anyway")
        }

        return try {
            // Try combined sync first, fall back to individual calls
            val result = tryCombinedSync()
            if (result != null) {
                result
            } else {
                Log.w(TAG, "Combined sync failed, falling back to individual calls")
                doWorkLegacy()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error syncing digests", e)
            retryOrFail()
        }
    }

    /**
     * Try using the combined /sync endpoint.
     * Returns null if it fails (so caller can fall back to legacy).
     */
    private suspend fun tryCombinedSync(): Result? {
        val existingRemoteIds = digestRepository.getAllRemoteIds()
        val lastFeedSyncTime = settingsRepository.getLastFeedSyncTime()
        val feedSince = if (lastFeedSyncTime > 0) lastFeedSyncTime else null

        val syncResult = ghostwriterRepository.performSync(feedSince, existingRemoteIds)

        return when (syncResult) {
            is GhostwriterResult.Success -> {
                val syncData = syncResult.data
                val newDigests = syncData.digests.newDigests
                val shouldDownloadEpubs = settingsRepository.shouldDownloadGhostwriterEpubsOnSync()

                Log.i(
                    TAG,
                    "Combined sync: ${newDigests.size} new digests " +
                            if (shouldDownloadEpubs) "to download" else "to index only"
                )

                val processedCount = downloadDigestsParallel(
                    digests = newDigests,
                    shouldDownloadEpubs = shouldDownloadEpubs
                )

                Log.i(TAG, "Processed $processedCount new digests via combined sync")
                settingsRepository.setLastDigestSyncTime(System.currentTimeMillis())
                Result.success()
            }
            is GhostwriterResult.Error -> {
                Log.w(TAG, "Combined sync endpoint failed: ${syncResult.message}")
                null // Signal to fall back
            }
            is GhostwriterResult.NotConfigured -> {
                Log.i(TAG, "Ghostwriter not configured")
                Result.success()
            }
        }
    }

    /**
     * Download or index digests in parallel with a concurrency limit of 3.
     */
    private suspend fun downloadDigestsParallel(
        digests: List<SyncDigest>,
        shouldDownloadEpubs: Boolean
    ): Int {
        if (digests.isEmpty()) return 0

        val semaphore = Semaphore(3)
        var processedCount = 0

        coroutineScope {
            val results = digests.map { digest ->
                async {
                    semaphore.withPermit {
                        if (shouldDownloadEpubs) {
                            downloadAndSaveDigest(digest)
                        } else {
                            saveDigestMetadataOnly(digest)
                        }
                    }
                }
            }
            processedCount = results.awaitAll().count { it }
        }

        return processedCount
    }

    /**
     * Download a single digest EPUB and save it with embedded articles.
     * Returns true if successful.
     */
    private suspend fun downloadAndSaveDigest(digest: SyncDigest): Boolean {
        val downloadResult = ghostwriterRepository.downloadDigest(digest.filename)

        return when (downloadResult) {
            is GhostwriterResult.Success -> {
                val file = downloadResult.data
                Log.i(TAG, "Downloaded: ${file.absolutePath}")

                val generatedAt = try {
                    digest.completedAt?.let { dateFormat.parse(it)?.time }
                        ?: System.currentTimeMillis()
                } catch (e: Exception) {
                    System.currentTimeMillis()
                }

                // Articles are already in the sync response
                val articles = digest.articles.ifEmpty { null }

                digestRepository.saveRemoteDigest(
                    remoteId = digest.id,
                    epubFilePath = file.absolutePath,
                    articleCount = digest.articleCount,
                    generatedAt = generatedAt,
                    period = digest.period,
                    articles = articles
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

                true
            }
            is GhostwriterResult.Error -> {
                Log.e(TAG, "Failed to download ${digest.filename}: ${downloadResult.message}")
                false
            }
            is GhostwriterResult.NotConfigured -> {
                Log.e(TAG, "Ghostwriter not configured during download")
                false
            }
        }
    }

    /**
     * Save digest metadata/articles without downloading the EPUB file.
     * The EPUB path still points to where the file will be downloaded on demand.
     */
    private suspend fun saveDigestMetadataOnly(digest: SyncDigest): Boolean {
        return try {
            val generatedAt = try {
                digest.completedAt?.let { dateFormat.parse(it)?.time } ?: System.currentTimeMillis()
            } catch (e: Exception) {
                System.currentTimeMillis()
            }

            val expectedPath = getExpectedEpubPath(digest.filename)
            val articles = digest.articles.ifEmpty { null }

            digestRepository.saveRemoteDigest(
                remoteId = digest.id,
                epubFilePath = expectedPath,
                articleCount = digest.articleCount,
                generatedAt = generatedAt,
                period = digest.period,
                articles = articles
            )

            Log.i(TAG, "Indexed digest without EPUB download: ${digest.id}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save digest metadata for ${digest.id}", e)
            false
        }
    }

    /**
     * Legacy sync using individual API calls (fallback).
     */
    private suspend fun doWorkLegacy(): Result {
        val digestsResult = ghostwriterRepository.listDigests()
        val shouldDownloadEpubs = settingsRepository.shouldDownloadGhostwriterEpubsOnSync()

        return when (digestsResult) {
            is GhostwriterResult.Success -> {
                val remoteDigests = digestsResult.data
                val existingRemoteIds = digestRepository.getAllRemoteIds().toSet()

                val newDigests = remoteDigests.filter { digest ->
                    digest.status == "completed" &&
                    digest.id !in existingRemoteIds
                }

                Log.i(
                    TAG,
                    "Legacy sync: ${newDigests.size} new digests " +
                            if (shouldDownloadEpubs) "to download" else "to index only"
                )

                var processedCount = 0
                for (digest in newDigests) {
                    if (!shouldDownloadEpubs) {
                        val generatedAt = try {
                            digest.completedAt?.let { dateFormat.parse(it)?.time }
                                ?: System.currentTimeMillis()
                        } catch (e: Exception) {
                            System.currentTimeMillis()
                        }

                        val articlesResult = ghostwriterRepository.getDigestArticles(digest.id)
                        val articles = when (articlesResult) {
                            is GhostwriterResult.Success -> articlesResult.data.articles
                            is GhostwriterResult.Error -> null
                            is GhostwriterResult.NotConfigured -> null
                        }

                        digestRepository.saveRemoteDigest(
                            remoteId = digest.id,
                            epubFilePath = getExpectedEpubPath(digest.filename),
                            articleCount = digest.articleCount,
                            generatedAt = generatedAt,
                            period = digest.period,
                            articles = articles
                        )
                        processedCount++
                        continue
                    }

                    val downloadResult = ghostwriterRepository.downloadDigest(digest.filename)

                    when (downloadResult) {
                        is GhostwriterResult.Success -> {
                            val file = downloadResult.data

                            val generatedAt = try {
                                digest.completedAt?.let { dateFormat.parse(it)?.time }
                                    ?: System.currentTimeMillis()
                            } catch (e: Exception) {
                                System.currentTimeMillis()
                            }

                            val articlesResult = ghostwriterRepository.getDigestArticles(digest.id)
                            val articles = when (articlesResult) {
                                is GhostwriterResult.Success -> articlesResult.data.articles
                                is GhostwriterResult.Error -> null
                                is GhostwriterResult.NotConfigured -> null
                            }

                            digestRepository.saveRemoteDigest(
                                remoteId = digest.id,
                                epubFilePath = file.absolutePath,
                                articleCount = digest.articleCount,
                                generatedAt = generatedAt,
                                period = digest.period,
                                articles = articles
                            )

                            when (val exportResult = epubExporter.exportToCustomDirectory(file)) {
                                is ExportResult.Success -> Log.i(TAG, "Exported to custom directory")
                                is ExportResult.PermissionRevoked -> Log.w(TAG, "Custom export permission revoked")
                                is ExportResult.Error -> Log.e(TAG, "Custom export failed: ${exportResult.message}")
                                ExportResult.NotConfigured -> { }
                            }

                            processedCount++
                        }
                        is GhostwriterResult.Error -> {
                            Log.e(TAG, "Failed to download ${digest.filename}: ${downloadResult.message}")
                        }
                        is GhostwriterResult.NotConfigured -> {
                            Log.e(TAG, "Ghostwriter not configured during download")
                        }
                    }
                }

                Log.i(TAG, "Legacy sync processed $processedCount digests")
                settingsRepository.setLastDigestSyncTime(System.currentTimeMillis())
                Result.success()
            }
            is GhostwriterResult.Error -> {
                Log.e(TAG, "Failed to list digests: ${digestsResult.message}")
                retryOrFail()
            }
            is GhostwriterResult.NotConfigured -> {
                Result.success()
            }
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

    private fun getExpectedEpubPath(filename: String): String {
        val documentsDir = File(applicationContext.getExternalFilesDir(null), "Epilogue")
        if (!documentsDir.exists()) {
            documentsDir.mkdirs()
        }
        return File(documentsDir, filename).absolutePath
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
