package com.example.epilogue.shared.sync

import kotlinx.datetime.Instant
import kotlinx.datetime.LocalDateTime
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toInstant

fun parseIso8601ToEpochMillis(timestamp: String?): Long? {
    if (timestamp.isNullOrBlank()) return null

    val normalized = timestamp.trim().replace(' ', 'T')

    val candidates = buildList {
        add(normalized)

        // Handle timezone-less timestamps from legacy server code paths.
        if (!normalized.endsWith("Z") &&
            !normalized.contains('+') &&
            !normalized.substringAfterLast('T', "").contains('-')
        ) {
            add("${normalized}Z")
        }
    }

    for (candidate in candidates) {
        try {
            return Instant.parse(candidate).toEpochMilliseconds()
        } catch (_: Exception) {
            // Try LocalDateTime fallback below.
        }

        try {
            return LocalDateTime.parse(candidate.removeSuffix("Z"))
                .toInstant(TimeZone.UTC)
                .toEpochMilliseconds()
        } catch (_: Exception) {
            // Try next candidate.
        }
    }

    return null
}

fun epochMillisToIso8601(epochMillis: Long): String {
    return Instant.fromEpochMilliseconds(epochMillis).toString()
}
