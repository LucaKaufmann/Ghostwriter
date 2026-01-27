package com.example.epilogue.domain.model

/**
 * Domain model representing a generated digest.
 */
data class Digest(
    val id: Long,
    val generatedAt: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val fidelityCount: Int,
    val triggerType: TriggerType,
    val feedNames: List<String>,
    val remoteId: String? = null,  // Ghostwriter digest ID if synced from backend
    val period: String? = null      // morning, noon, evening, or manual
) {
    /** Returns true if this digest was downloaded from Ghostwriter */
    val isFromGhostwriter: Boolean get() = remoteId != null

    /** Returns a display-friendly period name */
    val periodDisplay: String get() = when (period?.lowercase()) {
        "morning" -> "Morning"
        "noon" -> "Noon"
        "evening" -> "Evening"
        "manual" -> "Manual"
        else -> if (triggerType == TriggerType.MANUAL) "Manual" else "Scheduled"
    }
}
