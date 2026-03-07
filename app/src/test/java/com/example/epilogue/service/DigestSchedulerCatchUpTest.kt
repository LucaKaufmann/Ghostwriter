package com.example.epilogue.service

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
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
}
