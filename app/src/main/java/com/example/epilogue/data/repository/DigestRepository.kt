package com.example.epilogue.data.repository

import com.example.epilogue.data.local.DigestArticleEntity
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.DigestEntity
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.DigestArticle
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.TriggerType
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for managing digest history.
 */
@Singleton
class DigestRepository @Inject constructor(
    private val digestDao: DigestDao
) {
    companion object {
        const val MAX_RETAINED_DIGESTS = 30
    }

    /**
     * Get all digests ordered by most recent first.
     */
    fun getAllDigests(): Flow<List<Digest>> =
        digestDao.getAllDigests().map { entities ->
            entities.map { it.toDomain() }
        }

    /**
     * Get a specific digest by ID.
     */
    suspend fun getDigestById(id: Long): Digest? =
        digestDao.getDigestById(id)?.toDomain()

    /**
     * Get all articles for a digest.
     */
    suspend fun getArticlesForDigest(digestId: Long): List<DigestArticle> =
        digestDao.getArticlesForDigest(digestId).map { it.toDomain() }

    /**
     * Get articles for a digest as a Flow.
     */
    fun getArticlesForDigestFlow(digestId: Long): Flow<List<DigestArticle>> =
        digestDao.getArticlesForDigestFlow(digestId).map { entities ->
            entities.map { it.toDomain() }
        }

    /**
     * Save a new digest with its articles.
     *
     * @param articles The processed articles to save
     * @param feeds The feeds that were used (for feed name display)
     * @param epubFilePath The path to the generated EPUB file
     * @param triggerType Whether this was scheduled or manual
     * @return The ID of the created digest
     */
    suspend fun saveDigest(
        articles: List<ProcessedArticle>,
        feeds: List<Feed>,
        epubFilePath: String,
        triggerType: TriggerType
    ): Long {
        val briefingCount = articles.count { it.isSummary }
        val fidelityCount = articles.count { !it.isSummary }

        // Get unique feed names from the feeds list
        val feedNames = feeds.map { it.name }.distinct()

        val digestEntity = DigestEntity(
            generatedAt = System.currentTimeMillis(),
            epubFilePath = epubFilePath,
            articleCount = articles.size,
            briefingCount = briefingCount,
            fidelityCount = fidelityCount,
            triggerType = triggerType,
            feedNames = feedNames.joinToString(",")
        )

        // Map articles to entities
        // We try to match articles to feeds by URL, but fall back to "Unknown" if no match
        val articleEntities = articles.mapIndexed { index, article ->
            val feedName = feeds.find { feed ->
                article.originalUrl.contains(feed.url.removePrefix("https://").removePrefix("http://").split("/").firstOrNull() ?: "")
            }?.name ?: feedNames.firstOrNull() ?: "Unknown"

            DigestArticleEntity(
                digestId = 0, // Will be set by transaction
                title = article.title,
                author = article.author,
                content = article.content,
                originalUrl = article.originalUrl,
                isSummary = article.isSummary,
                feedName = feedName,
                sortOrder = index
            )
        }

        val digestId = digestDao.insertDigestWithArticles(digestEntity, articleEntities)

        // Cleanup old digests if we exceed the limit
        cleanupOldDigests()

        return digestId
    }

    /**
     * Delete a digest and its EPUB file.
     *
     * @param digest The digest to delete
     * @return true if the file was successfully deleted (or didn't exist)
     */
    suspend fun deleteDigest(digest: Digest): Boolean {
        // Delete EPUB file first
        val file = File(digest.epubFilePath)
        val fileDeleted = if (file.exists()) file.delete() else true

        // Delete from database (cascade will remove articles)
        digestDao.deleteDigestById(digest.id)

        return fileDeleted
    }

    /**
     * Remove old digests beyond the retention limit.
     */
    private suspend fun cleanupOldDigests() {
        val count = digestDao.getDigestCount()
        if (count > MAX_RETAINED_DIGESTS) {
            val excess = count - MAX_RETAINED_DIGESTS
            val oldDigests = digestDao.getOldestDigests(excess)
            oldDigests.forEach { digest ->
                // Delete file
                File(digest.epubFilePath).delete()
                // Delete from database
                digestDao.deleteDigest(digest)
            }
        }
    }
}
