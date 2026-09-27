package com.example.epilogue.data.local

import androidx.room.Database
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.RoomDatabase

/** Frozen deployed Room 8 shape. Keep independent of production entities during Room 9 work. */
@Entity(tableName = "feeds")
data class LegacyRoom8Feed(
    @PrimaryKey val url: String,
    val name: String,
    val mode: String,
    val lastFetched: Long,
    val maxArticles: Int,
    val isEnabled: Boolean,
    val serverUpdatedAt: Long?,
    val locallyModified: Boolean
)

@Entity(tableName = "digests")
data class LegacyRoom8Digest(
    @PrimaryKey(autoGenerate = true) val id: Long,
    val generatedAt: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val fidelityCount: Int,
    val triggerType: String,
    val feedNames: String,
    val remoteId: String?,
    val period: String?,
    val isComplete: Boolean,
    val errorMessage: String?
)

@Entity(
    tableName = "digest_articles",
    foreignKeys = [ForeignKey(
        entity = LegacyRoom8Digest::class,
        parentColumns = ["id"],
        childColumns = ["digestId"],
        onDelete = ForeignKey.CASCADE
    )],
    indices = [Index("digestId")]
)
data class LegacyRoom8DigestArticle(
    @PrimaryKey(autoGenerate = true) val id: Long,
    val digestId: Long,
    val title: String,
    val author: String,
    val content: String,
    val originalUrl: String,
    val isSummary: Boolean,
    val feedName: String,
    val sortOrder: Int
)

@Database(
    entities = [LegacyRoom8Feed::class, LegacyRoom8Digest::class, LegacyRoom8DigestArticle::class],
    version = 8,
    exportSchema = false
)
abstract class LegacyRoom8Database : RoomDatabase()
