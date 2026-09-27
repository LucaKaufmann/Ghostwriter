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
import androidx.work.Data
import com.codable.epilogue.R
import com.example.epilogue.data.repository.ArticleRepository
import com.example.epilogue.data.repository.ArticleDeliveryStore
import com.example.epilogue.data.repository.DeliveryClaimConflict
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.GenerationDiagnostics
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
import com.example.epilogue.domain.model.TriggerType
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.Date
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext

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
    private val settingsRepository: SettingsRepository,
    private val epubGenerator: EpubGenerator,
    private val epubExporter: EpubExporter,
    private val deliveryStore: ArticleDeliveryStore,
    private val generationGate: GenerationGate
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DailyDigestWorker"
        const val WORK_NAME = "daily_digest_work"

        // Input data keys
        const val KEY_FETCH_ALL = "fetch_all"  // Explicit user regeneration only.
        const val KEY_IS_MANUAL = "is_manual"  // If true, triggered manually (not scheduled)
        const val KEY_PERIOD = "period"  // Period name (MORNING, NOON, EVENING) for scheduled digests
        const val KEY_OCCURRENCE_DATE = "occurrence_date" // Explicit catch-up occurrence.
        private const val MAX_CONCURRENT_FEEDS = 3

        const val KEY_PERIODIC_ANCHOR = "periodic_anchor_millis"
        const val KEY_PERIODIC_ZONE = "periodic_zone_id"
        private const val PERIOD_MILLIS = 24L * 60 * 60 * 1000

        /** Latest nominal 24-hour slot, independent of constrained execution time. */
        internal fun periodicOccurrenceDate(now: ZonedDateTime, anchorMillis: Long,
            scheduleZone: ZoneId = now.zone): LocalDate {
            val elapsed = (now.toInstant().toEpochMilli() - anchorMillis).coerceAtLeast(0)
            val intended = Instant.ofEpochMilli(anchorMillis + (elapsed / PERIOD_MILLIS) * PERIOD_MILLIS)
            return intended.atZone(scheduleZone).toLocalDate()
        }

        /** Bounded fan-out, with results retained in the input feed order. */
        internal suspend fun <T, R> ingestInOrder(items: List<T>,
            block: suspend (T) -> R): List<R> = coroutineScope {
            val permits = Semaphore(MAX_CONCURRENT_FEEDS)
            items.map { item -> async { permits.withPermit { block(item) } } }.awaitAll()
        }

        // Notification constants for foreground service
        const val NOTIFICATION_CHANNEL_ID = "digest_generation"
        const val NOTIFICATION_ID = 1001

        // Retry configuration
        const val MAX_RETRY_ATTEMPTS = 3
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting daily digest generation (attempt ${runAttemptCount})")
        if (settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter is configured, skipping local digest generation")
            return Result.success()
        }
        try {
            setForeground(createForegroundInfo())
        } catch (e: IllegalStateException) {
            Log.w(TAG, "Could not start foreground service (app in background), continuing anyway")
        }
        return generationGate.run { generateLocal() }
    }

    private suspend fun generateLocal(): Result {
        var runId: Long? = null
        return try {
            val regeneration = inputData.getBoolean(KEY_FETCH_ALL, false)
            val isManual = inputData.getBoolean(KEY_IS_MANUAL, false)
            val periodName = inputData.getString(KEY_PERIOD)
            val period = periodName?.let {
                try {
                    DigestPeriod.valueOf(it)
                } catch (e: IllegalArgumentException) {
                    null
                }
            }

            val triggerType = if (isManual) TriggerType.MANUAL else TriggerType.SCHEDULED
            val periodString = period?.name?.lowercase() ?: if (isManual) "manual" else null
            val id = if (!isManual && period != null) {
                val explicit = inputData.getString(KEY_OCCURRENCE_DATE)
                    ?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                val anchor = inputData.getLong(KEY_PERIODIC_ANCHOR, 0L)
                val scheduleZone = inputData.getString(KEY_PERIODIC_ZONE)
                    ?.let { runCatching { ZoneId.of(it) }.getOrNull() }
                // A legacy attempt may finish before its periodic request is
                // updated with an anchor; retain its prior due-window rule.
                val now = ZonedDateTime.now()
                val occurrence = (explicit ?: if (anchor > 0)
                    periodicOccurrenceDate(now, anchor, scheduleZone ?: now.zone)
                    else if (now.hour < period.hour) now.toLocalDate().minusDays(1)
                    else now.toLocalDate()).toString()
                val executionKey = if (explicit != null) this.id.toString() else {
                    try {
                        PeriodicWorkExecution.key(applicationContext, this.id)
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (failure: Exception) {
                        Log.w(TAG, "Periodic execution identity unavailable")
                        null
                    }
                } ?: return retryOrFailure()
                deliveryStore.startScheduledRun(period.name, occurrence, executionKey,
                    retry = runAttemptCount > 0, regeneration = regeneration)
                    ?: return success("already_covered")
            } else deliveryStore.startRun(regeneration, if (isManual) "MANUAL" else null)
            runId = id
            val feeds = feedRepository.getEnabledFeedsList()
            val diagnostics = GenerationDiagnostics(ingestInOrder(feeds) { feed ->
                articleRepository.ingestForGeneration(feed, id, regeneration)
            })
            if (diagnostics.articles.isEmpty()) {
                deliveryStore.finishWithoutDigest(id, diagnostics.outcome, diagnostics.toJson(),
                    if (diagnostics.outcome in setOf("empty", "deferred")) diagnostics.exclusions
                    else emptyList())
                return if (diagnostics.outcome == "failed") retryOrFailure() else
                    success(diagnostics.outcome)
            }
            val result = epubGenerator.generate(diagnostics.articles.map { it.article },
                Date(), period)
            if (result == null) {
                deliveryStore.finishWithoutDigest(id, "failed",
                    """{"outcome":"failed","code":"epub_failed"}""")
                return retryOrFailure()
            }
            digestRepository.withGeneratedArtifact(result.file) {
                check(result.articles == diagnostics.articles.map { it.article })
                digestRepository.finalizeDeliveryRun(id, diagnostics,
                    result.file.absolutePath, triggerType, periodString, regeneration)
                // Optional export happens after the durable local commit.
                try {
                    when (val export = epubExporter.exportToCustomDirectory(result.file)) {
                        is ExportResult.Error -> Log.w(TAG, "Custom export failed: ${export.message}")
                        is ExportResult.PermissionRevoked -> Log.w(TAG, "Custom export permission revoked")
                        else -> Unit
                    }
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (failure: Exception) {
                    Log.w(TAG, "Optional export failed", failure)
                }
                success(diagnostics.outcome)
            }
        } catch (e: CancellationException) {
            runId?.let { id -> withContext(NonCancellable) {
                deliveryStore.finishWithoutDigest(id, "cancelled",
                    """{"outcome":"cancelled"}""")
            } }
            throw e
        } catch (e: DeliveryClaimConflict) {
            runId?.let { deliveryStore.finishWithoutDigest(it, "failed",
                """{"outcome":"failed","code":"claim_conflict"}""") }
            retryOrFailure()
        } catch (e: Exception) {
            Log.e(TAG, "Error generating digest", e)
            runId?.let { deliveryStore.finishWithoutDigest(it, "failed",
                """{"outcome":"failed","code":"generation_failed"}""") }
            if (e is IOException) retryOrFailure() else Result.failure()
        }
    }

    private fun retryOrFailure(): Result =
        if (runAttemptCount < MAX_RETRY_ATTEMPTS) Result.retry() else Result.failure()

    private fun success(outcome: String): Result = Result.success(Data.Builder()
        .putString("generation_outcome", outcome).build())

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
