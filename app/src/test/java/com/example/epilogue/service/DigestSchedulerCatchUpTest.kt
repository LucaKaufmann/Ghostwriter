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
    fun `periodic occurrence remains today when fall back moves execution before local hour`() {
        val beforeFallBack = ZonedDateTime.of(2026, 10, 24, 7, 0, 0, 0,
            java.time.ZoneId.of("Europe/Zurich"))
        val afterFallBack = beforeFallBack.plusHours(24)
        assertEquals(6, afterFallBack.hour)
        assertEquals(LocalDate.of(2026, 10, 25),
            DailyDigestWorker.periodicOccurrenceDate(afterFallBack, beforeFallBack.toInstant().toEpochMilli()))
        assertEquals(LocalDate.of(2026, 10, 26),
            DailyDigestWorker.periodicOccurrenceDate(afterFallBack.plusHours(24), beforeFallBack.toInstant().toEpochMilli()))
    }

    @Test
    fun `constrained periodic work retains prior evening occurrence across midnight`() {
        val scheduled = ZonedDateTime.of(2026, 3, 7, 18, 0, 0, 0, zone)
        val delayed = scheduled.plusHours(6).plusMinutes(30)
        assertEquals(LocalDate.of(2026, 3, 7), DailyDigestWorker.periodicOccurrenceDate(
            delayed, scheduled.toInstant().toEpochMilli()))
        assertEquals(LocalDate.of(2026, 3, 8), DailyDigestWorker.periodicOccurrenceDate(
            delayed.plusHours(24), scheduled.toInstant().toEpochMilli()))
    }

    @Test
    fun `long constrained periodic delay coalesces to latest nominal slot`() {
        val scheduled = ZonedDateTime.of(2026, 3, 7, 7, 0, 0, 0, zone)
        assertEquals(LocalDate.of(2026, 3, 9), DailyDigestWorker.periodicOccurrenceDate(
            scheduled.plusHours(50), scheduled.toInstant().toEpochMilli()))
    }
}
