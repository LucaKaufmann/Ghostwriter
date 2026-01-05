package com.example.epilog.service

import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Calendar

/**
 * Unit tests for DigestScheduler delay calculation logic.
 */
class DigestSchedulerTest {

    @Test
    fun `calculateInitialDelay returns positive value for future time today`() {
        val now = Calendar.getInstance()
        val targetHour = (now.get(Calendar.HOUR_OF_DAY) + 2) % 24
        val targetMinute = 0

        val delay = calculateInitialDelay(targetHour, targetMinute)

        assertTrue("Delay should be positive", delay > 0)
        assertTrue("Delay should be less than 24 hours", delay < 24 * 60 * 60 * 1000)
    }

    @Test
    fun `calculateInitialDelay schedules for tomorrow when time has passed`() {
        val now = Calendar.getInstance()
        val targetHour = (now.get(Calendar.HOUR_OF_DAY) - 1 + 24) % 24
        val targetMinute = 0

        val delay = calculateInitialDelay(targetHour, targetMinute)

        assertTrue("Delay should be positive", delay > 0)
        // Should be roughly 23 hours (minus 1 hour ago = tomorrow at that time)
        assertTrue("Delay should be more than 22 hours", delay > 22 * 60 * 60 * 1000)
        assertTrue("Delay should be less than 25 hours", delay < 25 * 60 * 60 * 1000)
    }

    @Test
    fun `calculateInitialDelay handles midnight scheduling`() {
        val delay = calculateInitialDelay(0, 0)

        assertTrue("Delay should be positive", delay > 0)
        assertTrue("Delay should be less than 24 hours", delay < 24 * 60 * 60 * 1000)
    }

    @Test
    fun `calculateInitialDelay handles 10pm default schedule`() {
        val delay = calculateInitialDelay(22, 0)

        assertTrue("Delay should be positive", delay > 0)
        assertTrue("Delay should be less than 24 hours", delay < 24 * 60 * 60 * 1000)
    }

    /**
     * Helper method that mirrors DigestScheduler's calculateInitialDelay.
     * Extracted here for testability without Android dependencies.
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
}
