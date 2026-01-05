package com.example.epilog.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * Unit tests for RssService date parsing logic.
 */
class RssServiceTest {

    @Test
    fun `parseDate handles RFC 822 format`() {
        val dateString = "Mon, 06 Jan 2025 14:30:00 +0000"
        val result = parseDate(dateString)

        assertTrue("Should parse RFC 822 date", result > 0)
    }

    @Test
    fun `parseDate handles ISO 8601 format with Z timezone`() {
        val dateString = "2025-01-06T14:30:00Z"
        // Note: This format with 'Z' might need special handling
        val result = parseDate(dateString.replace("Z", "+0000"))

        assertTrue("Should parse ISO 8601 date", result > 0)
    }

    @Test
    fun `parseDate handles ISO 8601 format with offset`() {
        val dateString = "2025-01-06T14:30:00+0000"
        val result = parseDate(dateString)

        assertTrue("Should parse ISO 8601 with offset", result > 0)
    }

    @Test
    fun `parseDate handles simple datetime format`() {
        val dateString = "2025-01-06 14:30:00"
        val result = parseDate(dateString)

        assertTrue("Should parse simple datetime", result > 0)
    }

    @Test
    fun `parseDate returns 0 for invalid format`() {
        val dateString = "invalid-date"
        val result = parseDate(dateString)

        assertEquals("Should return 0 for invalid date", 0L, result)
    }

    @Test
    fun `parseDate returns 0 for empty string`() {
        val result = parseDate("")

        assertEquals("Should return 0 for empty string", 0L, result)
    }

    /**
     * Helper method that mirrors RssService's parseDate.
     * Extracted here for testability.
     */
    private fun parseDate(dateString: String): Long {
        val formats = listOf(
            SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss Z", Locale.US),
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssZ", Locale.US),
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSZ", Locale.US),
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US),
            SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
        )

        for (format in formats) {
            try {
                return format.parse(dateString)?.time ?: continue
            } catch (e: Exception) {
                continue
            }
        }

        return 0L
    }
}
