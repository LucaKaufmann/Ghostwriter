package com.example.epilogue.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.TriggerType

/**
 * Room entity for storing digest metadata.
 */
@Entity(tableName = "digests")
data class DigestEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val generatedAt: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val fidelityCount: Int,
    val triggerType: TriggerType,
    val feedNames: String,  // Comma-separated feed names
    val remoteId: String? = null,  // Ghostwriter digest ID (UUID) if synced from backend
    val period: String? = null      // morning, noon, evening, or manual
) {
    fun toDomain(): Digest = Digest(
        id = id,
        generatedAt = generatedAt,
        epubFilePath = epubFilePath,
        articleCount = articleCount,
        briefingCount = briefingCount,
        fidelityCount = fidelityCount,
        triggerType = triggerType,
        feedNames = if (feedNames.isBlank()) emptyList() else feedNames.split(",").map { it.trim() },
        remoteId = remoteId,
        period = period
    )

    companion object {
        fun fromDomain(digest: Digest): DigestEntity = DigestEntity(
            id = digest.id,
            generatedAt = digest.generatedAt,
            epubFilePath = digest.epubFilePath,
            articleCount = digest.articleCount,
            briefingCount = digest.briefingCount,
            fidelityCount = digest.fidelityCount,
            triggerType = digest.triggerType,
            feedNames = digest.feedNames.joinToString(","),
            remoteId = digest.remoteId,
            period = digest.period
        )
    }
}
