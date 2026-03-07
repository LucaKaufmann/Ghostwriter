package com.example.epilogue.shared.sync

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class TimestampParsingTest {
    @Test
    fun parsesIsoFormatsWithAndWithoutTimezone() {
        val withZone = parseIso8601ToEpochMillis("2026-03-07T09:10:11Z")
        val withoutZone = parseIso8601ToEpochMillis("2026-03-07T09:10:11")
        val withMillis = parseIso8601ToEpochMillis("2026-03-07T09:10:11.123")
        val withSpace = parseIso8601ToEpochMillis("2026-03-07 09:10:11")

        assertNotNull(withZone)
        assertEquals(withZone, withoutZone)
        assertNotNull(withMillis)
        assertNotNull(withSpace)
    }

    @Test
    fun returnsNullForMalformedInput() {
        assertNull(parseIso8601ToEpochMillis("not-a-date"))
        assertNull(parseIso8601ToEpochMillis(null))
    }
}
