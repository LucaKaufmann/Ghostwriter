package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Transaction
import com.example.epilogue.domain.model.TriggerType
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/**
 * Data access object for digest operations.
 */
@Dao
interface DigestDao {

    @Query("SELECT * FROM digests ORDER BY generatedAt DESC")
    fun getAllDigests(): Flow<List<DigestEntity>>

    @Query("SELECT * FROM digests WHERE id = :id")
    suspend fun getDigestById(id: Long): DigestEntity?

    @Query("SELECT * FROM digest_articles WHERE digestId = :digestId ORDER BY sortOrder ASC")
    suspend fun getArticlesForDigest(digestId: Long): List<DigestArticleEntity>

    @Query("SELECT * FROM digest_articles WHERE digestId = :digestId ORDER BY sortOrder ASC")
    fun getArticlesForDigestFlow(digestId: Long): Flow<List<DigestArticleEntity>>

    @Insert
    suspend fun insertDigest(digest: DigestEntity): Long

    @Insert
    suspend fun insertArticles(articles: List<DigestArticleEntity>)

    @Query("DELETE FROM digest_articles WHERE digestId = :digestId")
    suspend fun deleteArticlesForDigest(digestId: Long)

    @Query(
        """
        UPDATE digests
        SET epubFilePath = :epubFilePath,
            articleCount = :articleCount,
            briefingCount = :briefingCount,
            fidelityCount = :fidelityCount,
            feedNames = :feedNames,
            isComplete = 1,
            errorMessage = NULL
        WHERE id = :id
        """
    )
    suspend fun markDigestCompleted(
        id: Long,
        epubFilePath: String,
        articleCount: Int,
        briefingCount: Int,
        fidelityCount: Int,
        feedNames: String
    )

    @Transaction
    suspend fun completeDigestWithArticles(
        digestId: Long,
        epubFilePath: String,
        articleCount: Int,
        briefingCount: Int,
        fidelityCount: Int,
        feedNames: String,
        articles: List<DigestArticleEntity>
    ) {
        markDigestCompleted(
            id = digestId,
            epubFilePath = epubFilePath,
            articleCount = articleCount,
            briefingCount = briefingCount,
            fidelityCount = fidelityCount,
            feedNames = feedNames
        )
        deleteArticlesForDigest(digestId)
        val articlesWithDigestId = articles.map { it.copy(digestId = digestId) }
        insertArticles(articlesWithDigestId)
    }

    @Query("UPDATE digests SET isComplete = 0, errorMessage = :errorMessage WHERE id = :id")
    suspend fun markDigestFailed(id: Long, errorMessage: String)

    @Transaction
    suspend fun insertDigestWithArticles(
        digest: DigestEntity,
        articles: List<DigestArticleEntity>
    ): Long {
        val digestId = insertDigest(digest)
        val articlesWithDigestId = articles.map { it.copy(digestId = digestId) }
        insertArticles(articlesWithDigestId)
        return digestId
    }

    @Delete
    suspend fun deleteDigest(digest: DigestEntity)

    @Query("DELETE FROM digests WHERE id = :id")
    suspend fun deleteDigestById(id: Long)

    @Query("SELECT EXISTS(SELECT 1 FROM digests WHERE epubFilePath = :path AND id != :excludingId)")
    suspend fun hasOtherArtifactReference(path: String, excludingId: Long): Boolean

    @Query("SELECT EXISTS(SELECT 1 FROM digests WHERE epubFilePath = :path)")
    suspend fun hasArtifactReference(path: String): Boolean

    /** Serialize the reference check and unlink with history writes. */
    @Transaction
    suspend fun removeUnreferencedArtifact(path: String, removeFile: (String) -> Boolean): Boolean {
        if (hasArtifactReference(path)) return false
        return removeFile(path)
    }

    /** Keep reference inspection and row deletion serialized with other Room writers. */
    @Transaction
    suspend fun deleteWithArtifact(id: Long, removeFile: (String) -> Boolean): Boolean {
        val digest = getDigestById(id) ?: return true
        if (digest.epubFilePath.isNotBlank() &&
            !hasOtherArtifactReference(digest.epubFilePath, id) &&
            !removeFile(digest.epubFilePath)
        ) return false
        deleteDigestById(id)
        return true
    }

    @Transaction
    suspend fun removeUnsharedArtifact(id: Long, removeFile: (String) -> Boolean): Boolean {
        val digest = getDigestById(id) ?: return false
        if (digest.epubFilePath.isBlank() || hasOtherArtifactReference(digest.epubFilePath, id)) return false
        return removeFile(digest.epubFilePath)
    }

    @Query("SELECT COUNT(*) FROM digests")
    suspend fun getDigestCount(): Int

    @Query("SELECT * FROM digests ORDER BY generatedAt ASC LIMIT :limit")
    suspend fun getOldestDigests(limit: Int): List<DigestEntity>

    @Query("SELECT * FROM digests")
    suspend fun getAllDigestsList(): List<DigestEntity>

    /** Clear the current snapshot; editions created later remain in history. */
    suspend fun deleteAllWithArtifacts(removeFile: (String) -> Boolean): Boolean {
        val snapshot = getAllDigestsList()
        var allDeleted = true
        for (digest in snapshot) {
            currentCoroutineContext().ensureActive()
            // Each completed unlink/row deletion commits before the next one.
            // Cancellation cannot roll back earlier rows after their files are gone.
            val deleted = withContext(NonCancellable) {
                deleteWithArtifact(digest.id, removeFile)
            }
            if (!deleted) allDeleted = false
        }
        return allDeleted
    }

    @Query("DELETE FROM digests")
    suspend fun deleteAllDigests()

    @Query("SELECT EXISTS(SELECT 1 FROM digests WHERE remoteId = :remoteId)")
    suspend fun existsByRemoteId(remoteId: String): Boolean

    @Query("SELECT remoteId FROM digests WHERE remoteId IS NOT NULL")
    suspend fun getAllRemoteIds(): List<String>

    @Query("SELECT * FROM digests WHERE remoteId IS NOT NULL")
    suspend fun getRemoteDigests(): List<DigestEntity>

    @Query("UPDATE digests SET epubFilePath = :epubFilePath WHERE id = :id")
    suspend fun updateEpubFilePath(id: Long, epubFilePath: String)

    /**
     * Check if a digest with similar content was created recently.
     * Used to prevent duplicate saves from race conditions.
     */
    @Query("SELECT EXISTS(SELECT 1 FROM digests WHERE generatedAt >= :sinceTime AND articleCount = :articleCount)")
    suspend fun existsRecentDigest(sinceTime: Long, articleCount: Int): Boolean

    @Query(
        "SELECT generatedAt FROM digests " +
            "WHERE triggerType = :triggerType AND period = :period " +
            "ORDER BY generatedAt DESC LIMIT 1"
    )
    suspend fun getLatestDigestTimestampForPeriod(
        triggerType: TriggerType,
        period: String
    ): Long?
}
