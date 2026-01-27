package com.example.epilogue.domain.model

/**
 * Represents the time periods when a digest can be generated.
 * Users can select multiple periods for daily digest generation.
 *
 * @property hour The hour of day (0-23) when the digest generation starts
 * @property displayTime User-friendly approximate delivery time (generation takes time)
 */
enum class DigestPeriod(val hour: Int, val displayTime: String) {
    MORNING(7, "7:00"),
    NOON(12, "12:00"),
    EVENING(18, "18:00");

    companion object {
        /**
         * Returns the period closest to the given hour.
         * Used for migrating from specific time to period-based scheduling.
         */
        fun fromHour(hour: Int): DigestPeriod {
            return when {
                hour < 10 -> MORNING
                hour < 17 -> NOON
                else -> EVENING
            }
        }
    }
}
