package com.example.epilog.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.example.epilog.domain.model.Digest
import com.example.epilog.domain.model.TriggerType

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
    val feedNames: String  // Comma-separated feed names
) {
    fun toDomain(): Digest = Digest(
        id = id,
        generatedAt = generatedAt,
        epubFilePath = epubFilePath,
        articleCount = articleCount,
        briefingCount = briefingCount,
        fidelityCount = fidelityCount,
        triggerType = triggerType,
        feedNames = if (feedNames.isBlank()) emptyList() else feedNames.split(",").map { it.trim() }
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
            feedNames = digest.feedNames.joinToString(",")
        )
    }
}
