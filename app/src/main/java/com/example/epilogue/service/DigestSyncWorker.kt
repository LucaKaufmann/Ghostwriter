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
import com.example.epilogue.data.remote.ghostwriter.DigestResponse
import com.example.epilogue.data.remote.ghostwriter.SyncDigest
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.shared.ghostwriter.DigestArticleResponse as SharedDigestArticleResponse
import com.example.epilogue.shared.sync.DigestSyncPlan
import com.example.epilogue.shared.sync.DigestSyncUseCase
import com.example.epilogue.shared.sync.SyncPortResult
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
 * Sync planning logic is in shared KMP DigestSyncUseCase.
 */
@HiltWorker
class DigestSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val ghostwriterRepository: GhostwriterRepository,
    private val digestRepository: DigestRepository,
    private val settingsRepository: SettingsRepository,
    private val epubExporter: EpubExporter,
    private val digestSyncUseCase: DigestSyncUseCase
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DigestSyncWorker"
        const val WORK_NAME = "digest_sync_work"
        const val WORK_NAME_IMMEDIATE = "digest_sync_immediate"

        const val NOTIFICATION_CHANNEL_ID = "digest_sync"
        const val NOTIFICATION_ID = 1002

        const val MAX_RETRY_ATTEMPTS = 3
        private const val REMOTE_EPUB_RETENTION_MILLIS = 30L * 24L * 60L * 60L * 1000L
    }

    private val dateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting digest sync from Ghostwriter (attempt ${runAttemptCount})")

        try {
            setForeground(createForegroundInfo())
        } catch (e: IllegalStateException) {
            Log.w(TAG, "Could not start foreground service (app in background), continuing anyway")
        }

        return try {
            when (val plan = digestSyncUseCase.planSync()) {
                is DigestSyncPlan.NotConfigured -> {
                    Log.i(TAG, "Ghostwriter not configured, skipping sync")
                    Result.success()
                }

                is DigestSyncPlan.Error -> {
                    Log.e(TAG, "Failed to create digest sync plan: ${plan.message}")
                    retryOrFail()
                }

                is DigestSyncPlan.Combined -> {
                    val processedCount = downloadDigestsParallel(
                        digests = plan.digests.map { it.toApp() },
                        shouldDownloadEpubs = plan.shouldDownloadEpubs
                    )
                    Log.i(TAG, "Processed $processedCount new digests via combined sync")
                    settingsRepository.setLastDigestSyncTime(System.currentTimeMillis())
                    runRemoteEpubCleanup()
                    Result.success()
                }

                is DigestSyncPlan.Legacy -> {
                    processLegacyDigests(
                        digests = plan.digests.map { it.toApp() },
                        shouldDownloadEpubs = plan.shouldDownloadEpubs
                    )
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error syncing digests", e)
            retryOrFail()
        }
    }

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

                val articles = digest.articles.ifEmpty { null }

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

    private suspend fun processLegacyDigests(
        digests: List<DigestResponse>,
        shouldDownloadEpubs: Boolean
    ): Result {
        Log.i(
            TAG,
            "Legacy sync: ${digests.size} new digests " +
                if (shouldDownloadEpubs) "to download" else "to index only"
        )

        var processedCount = 0
        for (digest in digests) {
            if (!shouldDownloadEpubs) {
                val generatedAt = try {
                    digest.completedAt?.let { dateFormat.parse(it)?.time }
                        ?: System.currentTimeMillis()
                } catch (e: Exception) {
                    System.currentTimeMillis()
                }

                val articlesResult = digestSyncUseCase.getDigestArticles(digest.id)
                val articles = when (articlesResult) {
                    is SyncPortResult.Success -> articlesResult.data.articles.map { it.toApp() }
                    is SyncPortResult.Error,
                    is SyncPortResult.NotConfigured -> null
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

                    val articlesResult = digestSyncUseCase.getDigestArticles(digest.id)
                    val articles = when (articlesResult) {
                        is SyncPortResult.Success -> articlesResult.data.articles.map { it.toApp() }
                        is SyncPortResult.Error,
                        is SyncPortResult.NotConfigured -> null
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
        runRemoteEpubCleanup()
        return Result.success()
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

    private suspend fun runRemoteEpubCleanup() {
        val deletedCount = digestRepository.cleanupStaleRemoteEpubFiles(REMOTE_EPUB_RETENTION_MILLIS)
        if (deletedCount > 0) {
            Log.i(TAG, "Cleaned up $deletedCount stale remote EPUB files")
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

private fun com.example.epilogue.shared.ghostwriter.SyncDigest.toApp(): SyncDigest = SyncDigest(
    id = id,
    filename = filename,
    availableFormats = availableFormats,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt,
    articles = articles.map { it.toApp() }
)

private fun com.example.epilogue.shared.ghostwriter.DigestResponse.toApp(): DigestResponse = DigestResponse(
    id = id,
    filename = filename,
    availableFormats = availableFormats,
    period = period,
    status = status,
    stage = stage,
    articleCount = articleCount,
    errorMessage = errorMessage,
    createdAt = createdAt,
    completedAt = completedAt
)

private fun SharedDigestArticleResponse.toApp(): com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse =
    com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse(
        id = id,
        title = title,
        url = url,
        mode = mode,
        wordCount = wordCount,
        content = content,
        contentHtml = contentHtml,
        author = author,
        feedTitle = feedTitle,
        sortOrder = sortOrder,
        aiFailed = aiFailed
    )
