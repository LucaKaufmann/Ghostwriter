package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

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

    @Query("SELECT COUNT(*) FROM digests")
    suspend fun getDigestCount(): Int

    @Query("SELECT * FROM digests ORDER BY generatedAt ASC LIMIT :limit")
    suspend fun getOldestDigests(limit: Int): List<DigestEntity>
}
