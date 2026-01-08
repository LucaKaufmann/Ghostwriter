package com.example.epilogue.data.local

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import com.example.epilogue.domain.model.DigestArticle

/**
 * Room entity for storing articles within a digest.
 * Uses foreign key to DigestEntity with cascade delete.
 */
@Entity(
    tableName = "digest_articles",
    foreignKeys = [
        ForeignKey(
            entity = DigestEntity::class,
            parentColumns = ["id"],
            childColumns = ["digestId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("digestId")]
)
data class DigestArticleEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val digestId: Long,
    val title: String,
    val author: String,
    val content: String,
    val originalUrl: String,
    val isSummary: Boolean,
    val feedName: String,
    val sortOrder: Int
) {
    fun toDomain(): DigestArticle = DigestArticle(
        id = id,
        title = title,
        author = author,
        content = content,
        originalUrl = originalUrl,
        isSummary = isSummary,
        feedName = feedName
    )

    companion object {
        fun fromProcessedArticle(
            digestId: Long,
            article: com.example.epilogue.domain.model.ProcessedArticle,
            feedName: String,
            sortOrder: Int
        ): DigestArticleEntity = DigestArticleEntity(
            digestId = digestId,
            title = article.title,
            author = article.author,
            content = article.content,
            originalUrl = article.originalUrl,
            isSummary = article.isSummary,
            feedName = feedName,
            sortOrder = sortOrder
        )
    }
}
