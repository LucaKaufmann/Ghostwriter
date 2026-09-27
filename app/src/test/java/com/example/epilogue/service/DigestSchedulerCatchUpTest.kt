package com.example.epilogue.service

import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime

class DigestSchedulerCatchUpTest {

    private val zone = ZoneId.of("Europe/Helsinki")

    @Test
    fun `shouldEnqueueCatchUp returns false before scheduled hour`() {
        val now = ZonedDateTime.of(2026, 3, 7, 6, 30, 0, 0, zone)

        val shouldEnqueue = DigestScheduler.shouldEnqueueCatchUp(
            now = now,
            periodHour = 7,
            latestScheduledDigestTimeMillis = null
        )

        assertFalse(shouldEnqueue)
    }

    @Test
    fun `shouldEnqueueCatchUp returns true when due and no prior digest`() {
        val now = ZonedDateTime.of(2026, 3, 7, 8, 0, 0, 0, zone)

        val shouldEnqueue = DigestScheduler.shouldEnqueueCatchUp(
            now = now,
            periodHour = 7,
            latestScheduledDigestTimeMillis = null
        )

        assertTrue(shouldEnqueue)
    }

    @Test
    fun `shouldEnqueueCatchUp returns false when digest already generated after scheduled time`() {
        val now = ZonedDateTime.of(2026, 3, 7, 8, 0, 0, 0, zone)
        val latestDigest = ZonedDateTime.of(2026, 3, 7, 7, 15, 0, 0, zone).toInstant().toEpochMilli()

        val shouldEnqueue = DigestScheduler.shouldEnqueueCatchUp(
            now = now,
            periodHour = 7,
            latestScheduledDigestTimeMillis = latestDigest
        )

        assertFalse(shouldEnqueue)
    }

    @Test
    fun `shouldEnqueueCatchUp returns true when latest digest is from previous day`() {
        val now = ZonedDateTime.of(2026, 3, 7, 8, 0, 0, 0, zone)
        val latestDigest = ZonedDateTime.of(2026, 3, 6, 21, 0, 0, 0, zone).toInstant().toEpochMilli()

        val shouldEnqueue = DigestScheduler.shouldEnqueueCatchUp(
            now = now,
            periodHour = 7,
            latestScheduledDigestTimeMillis = latestDigest
        )

        assertTrue(shouldEnqueue)
    }

    @Test
    fun `completed empty or deferred run suppresses catch up without digest history`() {
        val now = ZonedDateTime.of(2026, 3, 7, 8, 0, 0, 0, zone)
        assertFalse(DigestScheduler.shouldEnqueueCatchUp(now, 7, null,
            completedRun = true))
        assertTrue(DigestScheduler.shouldEnqueueCatchUp(now, 7, null,
            completedRun = false))
    }

    @Test
    fun `periodic admission uses latest due day when work starts after midnight`() {
        val beforeHour = ZonedDateTime.of(2026, 3, 8, 1, 0, 0, 0, zone)
        val afterHour = ZonedDateTime.of(2026, 3, 8, 8, 0, 0, 0, zone)
        assertEquals(LocalDate.of(2026, 3, 7),
            DailyDigestWorker.dueOccurrenceDate(beforeHour, 7))
        assertEquals(LocalDate.of(2026, 3, 8),
            DailyDigestWorker.dueOccurrenceDate(afterHour, 7))
    }
}
