package com.example.epilogue.data.repository

import com.example.epilogue.domain.model.DigestPeriod
import org.junit.Assert.assertEquals
import org.junit.Test

class SettingsRepositoryTest {

    @Test
    fun `parseSchedulePeriodsPreference defaults only missing preference to evening`() {
        assertEquals(
            setOf(DigestPeriod.EVENING),
            parseSchedulePeriodsPreference(null)
        )
    }

    @Test
    fun `parseSchedulePeriodsPreference preserves explicit empty selection`() {
        assertEquals(
            emptySet<DigestPeriod>(),
            parseSchedulePeriodsPreference("")
        )
    }

    @Test
    fun `parseSchedulePeriodsPreference ignores invalid period names`() {
        assertEquals(
            setOf(DigestPeriod.MORNING, DigestPeriod.NOON),
            parseSchedulePeriodsPreference("MORNING,BOGUS,NOON")
        )
    }
}
