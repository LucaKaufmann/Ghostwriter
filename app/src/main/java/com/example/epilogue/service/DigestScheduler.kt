package com.example.epilogue.service

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.Calendar
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages scheduling of the daily digest generation using WorkManager.
 * Supports multiple time periods (morning, noon, evening) with independent scheduling.
 */
@Singleton
class DigestScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository
) {

    companion object {
        private const val TAG = "DigestScheduler"
        private const val WORK_NAME_PREFIX = "daily_digest_"
        private const val IMMEDIATE_WORK_NAME = "daily_digest_immediate"
    }

    private val workManager: WorkManager
        get() = WorkManager.getInstance(context)

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

    /**
     * Schedules a digest for a specific period.
     */
    fun schedulePeriod(period: DigestPeriod) {
        val initialDelay = calculateInitialDelay(period.hour, 0)

        val inputData = Data.Builder()
            .putString(DailyDigestWorker.KEY_PERIOD, period.name)
            .build()

        val periodicWorkRequest = PeriodicWorkRequestBuilder<DailyDigestWorker>(
            repeatInterval = 24,
            repeatIntervalTimeUnit = TimeUnit.HOURS
        )
            .setConstraints(workConstraints)
            .setInitialDelay(initialDelay, TimeUnit.MILLISECONDS)
            .setInputData(inputData)
            .addTag(DailyDigestWorker.TAG)
            .addTag(period.name)
            .build()

        workManager.enqueueUniquePeriodicWork(
            getWorkName(period),
            ExistingPeriodicWorkPolicy.CANCEL_AND_REENQUEUE,
            periodicWorkRequest
        )

        val delayHours = initialDelay / (1000 * 60 * 60)
        val delayMinutes = (initialDelay / (1000 * 60)) % 60
        Log.i(TAG, "Scheduled ${period.name} digest for ${period.hour}:00, " +
                "initial delay: ${delayHours}h ${delayMinutes}m")
    }

    /**
     * Cancels the scheduled digest for a specific period.
     */
    fun cancelPeriod(period: DigestPeriod) {
        workManager.cancelUniqueWork(getWorkName(period))
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
     * Triggers an immediate digest generation.
     * Uses expedited work for higher priority execution.
     *
     * @param fetchAll If true, fetches all articles regardless of lastFetched timestamp
     */
    fun runNow(fetchAll: Boolean = false) {
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
    fun getImmediateWorkInfo() = workManager.getWorkInfosForUniqueWorkLiveData(IMMEDIATE_WORK_NAME)
}
