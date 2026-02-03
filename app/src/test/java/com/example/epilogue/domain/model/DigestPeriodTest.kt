package com.example.epilogue.domain.model

import org.junit.Assert.assertEquals
import org.junit.Test

class DigestPeriodTest {

    @Test
    fun `fromHour maps early hours to morning`() {
        assertEquals(DigestPeriod.MORNING, DigestPeriod.fromHour(0))
        assertEquals(DigestPeriod.MORNING, DigestPeriod.fromHour(9))
    }

    @Test
    fun `fromHour maps mid hours to noon`() {
        assertEquals(DigestPeriod.NOON, DigestPeriod.fromHour(10))
        assertEquals(DigestPeriod.NOON, DigestPeriod.fromHour(16))
    }

    @Test
    fun `fromHour maps late hours to evening`() {
        assertEquals(DigestPeriod.EVENING, DigestPeriod.fromHour(17))
        assertEquals(DigestPeriod.EVENING, DigestPeriod.fromHour(23))
    }
}
