package com.example.epilogue.service

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.Operation
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.ArticleDeliveryStore
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
import dagger.hilt.android.qualifiers.ApplicationContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Calendar
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.Executor
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Manages scheduling of the daily digest generation using WorkManager.
 * Supports multiple time periods (morning, noon, evening) with independent scheduling.
 *
 * When Ghostwriter is configured, scheduled digests are still handled locally
 * (WorkManager triggers at the scheduled time), but the actual generation
 * can be delegated to the backend. Manual triggers from the UI are handled
 * by the ViewModel which decides between local and backend generation.
 */
@Singleton
class DigestScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository,
    private val digestRepository: DigestRepository,
    private val deliveryStore: ArticleDeliveryStore
) {

    companion object {
        private const val TAG = "DigestScheduler"
        private const val WORK_NAME_PREFIX = "daily_digest_"
        // Existing anchored requests keep their original input and occurrence reference.
        internal const val ANCHOR_TAG = "daily_digest_anchor_v1"
        private const val CATCH_UP_WORK_NAME_PREFIX = "daily_digest_catchup_"
        private const val CATCH_UP_TAG = "catch_up"
        private const val IMMEDIATE_WORK_NAME = "daily_digest_immediate"
        private const val SYNC_WORK_NAME = "digest_sync_periodic"
        private const val SYNC_INTERVAL_MINUTES = 30L
        private const val FEED_SYNC_WORK_NAME = "feed_sync_periodic"
        private const val FEED_SYNC_INTERVAL_MINUTES = 15L
        private val CATCH_UP_DATE_FORMAT: DateTimeFormatter = DateTimeFormatter.BASIC_ISO_DATE

        internal fun shouldEnqueueCatchUp(
            now: ZonedDateTime,
            periodHour: Int,
            latestScheduledDigestTimeMillis: Long?,
            completedRun: Boolean = false
        ): Boolean {
            if (completedRun) return false
            val scheduledTimeToday = now.toLocalDate()
                .atTime(periodHour, 0)
                .atZone(now.zone)
            if (now.isBefore(scheduledTimeToday)) {
                return false
            }

            if (latestScheduledDigestTimeMillis == null) {
                return true
            }

            val latestScheduledDigestTime = Instant.ofEpochMilli(latestScheduledDigestTimeMillis)
                .atZone(now.zone)
            return latestScheduledDigestTime.isBefore(scheduledTimeToday)
        }
    }

    private val workManager: WorkManager
        get() = WorkManager.getInstance(context)
    private val registrationLock = Any()
    private val registrationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val registrationJobs = mutableMapOf<DigestPeriod, Job>()
    private val registrationGenerations = mutableMapOf<DigestPeriod, Long>()
    private val pendingCancellations = mutableMapOf<DigestPeriod, MutableList<Operation>>()

    /**
     * Constraints for digest generation:
     * - Requires network connectivity
     * - No battery constraint (e-ink devices often report low battery)
     */
    private val workConstraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /**
     * Returns the unique work name for a given period.
     */
    private fun getWorkName(period: DigestPeriod): String {
        return "$WORK_NAME_PREFIX${period.name}"
    }

    private fun getCatchUpWorkName(period: DigestPeriod, date: LocalDate): String {
        return "$CATCH_UP_WORK_NAME_PREFIX${period.name}_${date.format(CATCH_UP_DATE_FORMAT)}"
    }

    /**
     * Schedules digests for all selected periods.
     * Cancels any previously scheduled periods that are no longer selected.
     */
    fun scheduleAllPeriods() {
        val selectedPeriods = settingsRepository.getSchedulePeriods()

        // Schedule selected periods
        for (period in selectedPeriods) {
            schedulePeriod(period)
        }

        // Cancel unselected periods
        for (period in DigestPeriod.entries) {
            if (period !in selectedPeriods) {
                cancelPeriod(period)
            }
        }

        Log.i(TAG, "Scheduled periods: ${selectedPeriods.joinToString { it.name }}")
    }

    /** Boot keeps its broadcast open until selected requests are durable. */
    suspend fun scheduleAllPeriodsAwaitPersistence() {
        val selectedPeriods = settingsRepository.getSchedulePeriods()
        // Cancel from this snapshot before waiting. A later user enable may then
        // register its own work without a stale boot callback cancelling it.
        for (period in DigestPeriod.entries) {
            if (period !in selectedPeriods) cancelPeriod(period)
        }
        coroutineScope {
            selectedPeriods.map { period ->
                async {
                    val generation = synchronized(registrationLock) {
                        if (period !in settingsRepository.getSchedulePeriods()) return@synchronized null
                        registrationJobs.remove(period)?.cancel()
                        ((registrationGenerations[period] ?: 0L) + 1).also {
                            registrationGenerations[period] = it
                        }
                    } ?: return@async
                    registerPeriod(period, generation, awaitPersistence = true,
                        waitForRunning = false)
                }
            }.awaitAll()
        }
    }

    /**
     * Schedules a digest for a specific period.
     */
    fun schedulePeriod(period: DigestPeriod) {
        synchronized(registrationLock) {
            registrationJobs.remove(period)?.cancel()
            val generation = (registrationGenerations[period] ?: 0L) + 1
            registrationGenerations[period] = generation
            registrationJobs[period] = registrationScope.launch {
                registerPeriod(period, generation)
            }
        }
    }

    private suspend fun registerPeriod(period: DigestPeriod, generation: Long,
        awaitPersistence: Boolean = false, waitForRunning: Boolean = true) {
        val manager = workManager
        val workName = getWorkName(period)
        val cancellations = synchronized(registrationLock) {
            pendingCancellations[period]?.toList().orEmpty()
        }
        val settled = mutableListOf<Operation>()
        // Await every outstanding cancellation; a later receipt alone does not
        // prove an earlier cancellation has finished removing its request.
        for (cancellation in cancellations) {
            try {
                cancellation.awaitPersistence()
                settled.add(cancellation)
            } catch (error: Exception) {
                currentCoroutineContext().ensureActive()
                // A completed failed receipt is no longer useful. Leave any later
                // still-pending cancellations for the next registration to await.
                settled.add(cancellation)
                synchronized(registrationLock) {
                    pendingCancellations[period]?.removeAll(settled.toSet())
                    if (pendingCancellations[period]?.isEmpty() == true)
                        pendingCancellations.remove(period)
                }
                Log.w(TAG, "Could not confirm ${period.name} cancellation", error)
                return
            }
        }
        synchronized(registrationLock) {
            pendingCancellations[period]?.removeAll(settled.toSet())
            if (pendingCancellations[period]?.isEmpty() == true) pendingCancellations.remove(period)
            if (registrationGenerations[period] != generation) return
        }
        val existing = try {
            // An already-running legacy worker keeps its original input. Wait for
            // the next ENQUEUED generation rather than interrupting that run.
            manager.getWorkInfosForUniqueWorkFlow(workName).first { rows ->
                val active = rows.firstOrNull { it.state !in setOf(
                    WorkInfo.State.SUCCEEDED, WorkInfo.State.FAILED, WorkInfo.State.CANCELLED) }
                active == null || ANCHOR_TAG in active.tags ||
                    (!waitForRunning && active.state == WorkInfo.State.RUNNING) ||
                    (active.state == WorkInfo.State.ENQUEUED &&
                        active.nextScheduleTimeMillis in 1L until Long.MAX_VALUE)
            }.firstOrNull { it.state !in setOf(
                WorkInfo.State.SUCCEEDED, WorkInfo.State.FAILED, WorkInfo.State.CANCELLED) }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            Log.w(TAG, "Could not inspect ${period.name} periodic schedule", error)
            null // KEEP preserves any existing work if the read failed.
        }
        if (!waitForRunning && existing?.state == WorkInfo.State.RUNNING && ANCHOR_TAG !in existing.tags) {
            // Already persisted. Keep the ordinary callback for its next ENQUEUED iteration.
            schedulePeriod(period)
            return
        }
        // Its input already carries the original 24-hour reference. Replacing
        // it with a post-run nextScheduleTime would shift late occurrences.
        if (existing != null && ANCHOR_TAG in existing.tags) return

        val initialDelay = calculateInitialDelay(period.hour, 0)
        val anchor = existing?.nextScheduleTimeMillis ?: System.currentTimeMillis() + initialDelay
        val builder = PeriodicWorkRequestBuilder<DailyDigestWorker>(24, TimeUnit.HOURS)
            .setConstraints(workConstraints)
            .setInputData(Data.Builder()
                .putString(DailyDigestWorker.KEY_PERIOD, period.name)
                .putLong(DailyDigestWorker.KEY_PERIODIC_ANCHOR, anchor)
                .putString(DailyDigestWorker.KEY_PERIODIC_ZONE, ZoneId.systemDefault().id)
                .build())
            .addTag(DailyDigestWorker.TAG)
            .addTag(period.name)
            .addTag(ANCHOR_TAG)
        if (existing == null) builder.setInitialDelay(initialDelay, TimeUnit.MILLISECONDS)
        else {
            builder.setId(existing.id)
            builder.setNextScheduleTimeOverride(anchor)
        }
        val request = builder.build()
        val operation = synchronized(registrationLock) {
            if (registrationGenerations[period] != generation) return
            manager.enqueueUniquePeriodicWork(workName,
                if (existing == null) ExistingPeriodicWorkPolicy.KEEP else ExistingPeriodicWorkPolicy.UPDATE,
                request)
        }
        if (awaitPersistence) operation.awaitPersistence()
        Log.i(TAG, "Registered ${period.name} digest occurrence at $anchor")
    }

    private suspend fun Operation.awaitPersistence() = suspendCancellableCoroutine<Unit> { continuation ->
        val receipt = result
        receipt.addListener({
            try {
                receipt.get()
                continuation.resume(Unit)
            } catch (error: Exception) {
                continuation.resumeWithException(error)
            }
        }, Executor { command -> command.run() })
    }

    /**
     * Cancels the scheduled digest for a specific period.
     */
    fun cancelPeriod(period: DigestPeriod) {
        synchronized(registrationLock) {
            registrationGenerations[period] = (registrationGenerations[period] ?: 0L) + 1
            registrationJobs.remove(period)?.cancel()
            pendingCancellations.getOrPut(period) { mutableListOf() }
                .add(workManager.cancelUniqueWork(getWorkName(period)))
        }
        Log.i(TAG, "Cancelled ${period.name} digest")
    }

    /**
     * Cancels all scheduled digests.
     */
    fun cancelAllPeriods() {
        for (period in DigestPeriod.entries) {
            cancelPeriod(period)
        }
    }

    /**
     * Updates scheduling for a specific period based on enabled state.
     */
    suspend fun updatePeriod(period: DigestPeriod, enabled: Boolean) {
        settingsRepository.toggleSchedulePeriod(period, enabled)
        if (enabled) {
            schedulePeriod(period)
        } else {
            cancelPeriod(period)
        }
    }

    /**
     * Enqueues catch-up work for periods whose scheduled time has already passed today
     * but no scheduled digest has been generated yet. Runs once per period per day.
     */
    suspend fun enqueueMissedPeriodCatchUps() {
        if (settingsRepository.isGhostwriterConfigured()) {
            Log.d(TAG, "Ghostwriter configured, skipping local catch-up checks")
            return
        }

        val now = ZonedDateTime.now()
        val today = now.toLocalDate()
        val selectedPeriods = settingsRepository.getSchedulePeriods()

        for (period in selectedPeriods) {
            val lastCatchUpDate = settingsRepository.getLastCatchUpDate(period)
            if (lastCatchUpDate == today.toString()) {
                continue
            }

            val completedRun = deliveryStore.coversScheduled(period.name, today.toString())
            val latestScheduledDigestTime = digestRepository.getLatestScheduledDigestTimeForPeriod(period)
            if (!shouldEnqueueCatchUp(now, period.hour, latestScheduledDigestTime, completedRun)) {
                continue
            }

            val inputData = Data.Builder()
                .putString(DailyDigestWorker.KEY_PERIOD, period.name)
                .putString(DailyDigestWorker.KEY_OCCURRENCE_DATE, today.toString())
                .build()

            val catchUpRequest = OneTimeWorkRequestBuilder<DailyDigestWorker>()
                .setConstraints(workConstraints)
                .setInputData(inputData)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .addTag(DailyDigestWorker.TAG)
                .addTag(period.name)
                .addTag(CATCH_UP_TAG)
                .build()

            val workName = getCatchUpWorkName(period, today)
            workManager.enqueueUniqueWork(workName, ExistingWorkPolicy.KEEP, catchUpRequest)
            settingsRepository.setLastCatchUpDate(period, today.toString())
            Log.i(TAG, "Enqueued catch-up digest for ${period.name} (workName=$workName)")
        }
    }

    /**
     * Triggers an immediate digest generation.
     * Uses expedited work for higher priority execution.
     *
     * @param fetchAll Explicit regeneration that may repeat already delivered articles.
     */
    fun runNow(fetchAll: Boolean = false): UUID {
        Log.i(TAG, "Triggering immediate digest generation (fetchAll=$fetchAll)")

        val inputData = Data.Builder()
            .putBoolean(DailyDigestWorker.KEY_FETCH_ALL, fetchAll)
            .putBoolean(DailyDigestWorker.KEY_IS_MANUAL, true)
            .build()

        val oneTimeWorkRequest = OneTimeWorkRequestBuilder<DailyDigestWorker>()
            .setConstraints(workConstraints)
            .setInputData(inputData)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .addTag(DailyDigestWorker.TAG)
            .build()

        workManager.enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            oneTimeWorkRequest
        )
        return oneTimeWorkRequest.id
    }

    /**
     * Calculates the initial delay until the next occurrence of the scheduled time.
     *
     * @param targetHour Target hour (0-23)
     * @param targetMinute Target minute (0-59)
     * @return Delay in milliseconds
     */
    private fun calculateInitialDelay(targetHour: Int, targetMinute: Int): Long {
        val now = Calendar.getInstance()
        val target = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, targetHour)
            set(Calendar.MINUTE, targetMinute)
            set(Calendar.SECOND, 0)
            set(Calendar.MILLISECOND, 0)
        }

        // If target time has already passed today, schedule for tomorrow
        if (target.before(now) || target == now) {
            target.add(Calendar.DAY_OF_MONTH, 1)
        }

        return target.timeInMillis - now.timeInMillis
    }

    /**
     * Gets the work status for immediate digest generation.
     */
    fun getImmediateWorkInfo(id: UUID) = workManager.getWorkInfoByIdLiveData(id)

    /**
     * Checks if Ghostwriter backend should be used for digest generation.
     * Returns true if Ghostwriter is enabled and has a valid URL configured.
     */
    fun shouldUseGhostwriter(): Boolean {
        return settingsRepository.isGhostwriterConfigured()
    }

    // ===== Digest Sync from Ghostwriter =====

    /**
     * Schedules periodic sync of digests from Ghostwriter.
     * Should be called when Ghostwriter is enabled.
     */
    fun scheduleDigestSync() {
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, not scheduling sync")
            return
        }

        val periodicWorkRequest = PeriodicWorkRequestBuilder<DigestSyncWorker>(
            repeatInterval = SYNC_INTERVAL_MINUTES,
            repeatIntervalTimeUnit = TimeUnit.MINUTES
        )
            .setConstraints(workConstraints)
            .addTag(DigestSyncWorker.TAG)
            .build()

        workManager.enqueueUniquePeriodicWork(
            SYNC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            periodicWorkRequest
        )

        Log.i(TAG, "Scheduled periodic digest sync every $SYNC_INTERVAL_MINUTES minutes")
    }

    /**
     * Cancels periodic digest sync.
     * Should be called when Ghostwriter is disabled.
     */
    fun cancelDigestSync() {
        workManager.cancelUniqueWork(SYNC_WORK_NAME)
        Log.i(TAG, "Cancelled periodic digest sync")
    }

    /**
     * Triggers an immediate digest sync from Ghostwriter.
     * Useful on app launch or when user manually requests sync.
     */
    fun syncDigestsNow() {
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, not syncing")
            return
        }

        Log.i(TAG, "Triggering immediate digest sync")

        val oneTimeWorkRequest = OneTimeWorkRequestBuilder<DigestSyncWorker>()
            .setConstraints(workConstraints)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .addTag(DigestSyncWorker.TAG)
            .build()

        workManager.enqueueUniqueWork(
            DigestSyncWorker.WORK_NAME_IMMEDIATE,
            ExistingWorkPolicy.REPLACE,
            oneTimeWorkRequest
        )
    }

    // ===== Feed Sync with Ghostwriter =====

    /**
     * Schedules periodic bi-directional feed sync with Ghostwriter.
     * Should be called when Ghostwriter is enabled.
     */
    fun scheduleFeedSync() {
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, not scheduling feed sync")
            return
        }

        val periodicWorkRequest = PeriodicWorkRequestBuilder<FeedSyncWorker>(
            repeatInterval = FEED_SYNC_INTERVAL_MINUTES,
            repeatIntervalTimeUnit = TimeUnit.MINUTES
        )
            .setConstraints(workConstraints)
            .addTag(FeedSyncWorker.TAG)
            .build()

        workManager.enqueueUniquePeriodicWork(
            FEED_SYNC_WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            periodicWorkRequest
        )

        Log.i(TAG, "Scheduled periodic feed sync every $FEED_SYNC_INTERVAL_MINUTES minutes")
    }

    /**
     * Cancels periodic feed sync.
     * Should be called when Ghostwriter is disabled.
     */
    fun cancelFeedSync() {
        workManager.cancelUniqueWork(FEED_SYNC_WORK_NAME)
        Log.i(TAG, "Cancelled periodic feed sync")
    }

    /**
     * Triggers an immediate bi-directional feed sync with Ghostwriter.
     * Useful on app launch, after local feed changes, or on manual refresh.
     */
    fun syncFeedsNow() {
        if (!settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter not configured, not syncing feeds")
            return
        }

        Log.i(TAG, "Triggering immediate feed sync")

        val oneTimeWorkRequest = OneTimeWorkRequestBuilder<FeedSyncWorker>()
            .setConstraints(workConstraints)
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .addTag(FeedSyncWorker.TAG)
            .build()

        workManager.enqueueUniqueWork(
            FeedSyncWorker.WORK_NAME_IMMEDIATE,
            ExistingWorkPolicy.REPLACE,
            oneTimeWorkRequest
        )
    }
}
