package com.example.epilogue.service

import android.content.Context
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.example.epilogue.data.repository.SettingsRepository
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.Calendar
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages scheduling of the daily digest generation using WorkManager.
 */
@Singleton
class DigestScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
    private val settingsRepository: SettingsRepository
) {

    companion object {
        private const val PERIODIC_WORK_NAME = "daily_digest_periodic"
        private const val IMMEDIATE_WORK_NAME = "daily_digest_immediate"
    }

    private val workManager: WorkManager
        get() = WorkManager.getInstance(context)

    /**
     * Constraints for digest generation:
     * - Requires network connectivity
     * - Battery should not be low
     */
    private val workConstraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresBatteryNotLow(true)
        .build()

    /**
     * Schedules the daily digest to run at the configured time.
     * Uses a periodic work request that runs approximately every 24 hours.
     */
    fun scheduleDailyDigest() {
        val hour = settingsRepository.getScheduleHour()
        val minute = settingsRepository.getScheduleMinute()

        val initialDelay = calculateInitialDelay(hour, minute)

        val periodicWorkRequest = PeriodicWorkRequestBuilder<DailyDigestWorker>(
            repeatInterval = 24,
            repeatIntervalTimeUnit = TimeUnit.HOURS
        )
            .setConstraints(workConstraints)
            .setInitialDelay(initialDelay, TimeUnit.MILLISECONDS)
            .build()

        workManager.enqueueUniquePeriodicWork(
            PERIODIC_WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            periodicWorkRequest
        )
    }

    /**
     * Cancels the scheduled daily digest.
     */
    fun cancelDailyDigest() {
        workManager.cancelUniqueWork(PERIODIC_WORK_NAME)
    }

    /**
     * Triggers an immediate digest generation.
     * Useful for "Run Now" functionality.
     *
     * @param fetchAll If true, fetches all articles regardless of lastFetched timestamp
     */
    fun runNow(fetchAll: Boolean = false) {
        val inputData = Data.Builder()
            .putBoolean(DailyDigestWorker.KEY_FETCH_ALL, fetchAll)
            .putBoolean(DailyDigestWorker.KEY_IS_MANUAL, true)
            .build()

        val oneTimeWorkRequest = OneTimeWorkRequestBuilder<DailyDigestWorker>()
            .setConstraints(workConstraints)
            .setInputData(inputData)
            .build()

        workManager.enqueueUniqueWork(
            IMMEDIATE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            oneTimeWorkRequest
        )
    }

    /**
     * Updates the schedule time and reschedules the work.
     *
     * @param hour Hour of day (0-23)
     * @param minute Minute of hour (0-59)
     */
    suspend fun updateScheduleTime(hour: Int, minute: Int) {
        settingsRepository.setScheduleTime(hour, minute)
        scheduleDailyDigest()
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
     * Gets the current work status for the daily digest.
     */
    fun getWorkInfo() = workManager.getWorkInfosForUniqueWorkLiveData(PERIODIC_WORK_NAME)

    /**
     * Gets the work status for immediate digest generation.
     */
    fun getImmediateWorkInfo() = workManager.getWorkInfosForUniqueWorkLiveData(IMMEDIATE_WORK_NAME)
}
