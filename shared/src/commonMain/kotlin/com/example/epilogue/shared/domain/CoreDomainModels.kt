package com.example.epilogue.shared.domain

import kotlinx.serialization.Serializable

@Serializable
enum class ProcessingMode {
    FIDELITY,
    BRIEFING
}

@Serializable
enum class TriggerType {
    SCHEDULED,
    MANUAL,
    TEST,
    GHOSTWRITER
}

@Serializable
enum class DigestPeriod(val hour: Int, val displayTime: String) {
    MORNING(7, "7:00"),
    NOON(12, "12:00"),
    EVENING(18, "18:00");

    companion object {
        fun fromHour(hour: Int): DigestPeriod {
            return when {
                hour < 10 -> MORNING
                hour < 17 -> NOON
                else -> EVENING
            }
        }
    }
}

@Serializable
data class Feed(
    val url: String,
    val name: String,
    val mode: ProcessingMode,
    val lastFetchedEpochMillis: Long = 0L,
    val maxArticles: Int = 0,
    val isEnabled: Boolean = true,
    val serverUpdatedAtEpochMillis: Long? = null,
    val locallyModified: Boolean = false
)

@Serializable
data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String,
    val originalUrl: String,
    val isSummary: Boolean,
    val feedUrl: String = "",
    val feedName: String = "",
    val publishedAtEpochMillis: Long? = null,
    val wordCount: Int = 0
)

@Serializable
data class DigestArticle(
    val id: String,
    val title: String,
    val author: String,
    val content: String,
    val originalUrl: String,
    val feedUrl: String = "",
    val feedName: String,
    val isSummary: Boolean,
    val orderIndex: Int = 0,
    val publishedAtEpochMillis: Long? = null,
    val wordCount: Int = 0
)

@Serializable
data class Digest(
    val id: String,
    val generatedAtEpochMillis: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val deepDiveCount: Int,
    val triggerType: TriggerType,
    val feedNames: List<String>,
    val remoteId: String? = null,
    val period: String? = null,
    val isComplete: Boolean = true,
    val errorMessage: String? = null
) {
    val isFromGhostwriter: Boolean get() = remoteId != null

    private val isTransientLocalScheduledDigest: Boolean
        get() = !isFromGhostwriter &&
            triggerType == TriggerType.SCHEDULED &&
            articleCount == 0 &&
            errorMessage.isNullOrBlank()

    val isProcessing: Boolean
        get() = (!isComplete && errorMessage.isNullOrBlank()) || isTransientLocalScheduledDigest

    val isFailed: Boolean
        get() = !isComplete && !errorMessage.isNullOrBlank()
}
