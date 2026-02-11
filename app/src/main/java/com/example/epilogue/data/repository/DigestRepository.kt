package com.example.epilogue.data.repository

import android.util.Log
import com.example.epilogue.data.local.DigestArticleEntity
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.DigestEntity
import com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse
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
     * @param period The digest period (morning, noon, evening, manual)
     * @return The ID of the created digest
     */
    suspend fun saveDigest(
        articles: List<ProcessedArticle>,
        feeds: List<Feed>,
        epubFilePath: String,
        triggerType: TriggerType,
        period: String? = null
    ): Long {
        // Prevent duplicate saves by checking if a digest with similar content was created recently
        val recentCutoff = System.currentTimeMillis() - (5 * 60 * 1000) // 5 minutes
        if (digestDao.existsRecentDigest(recentCutoff, articles.size)) {
            Log.d("DigestRepository", "Similar digest (${articles.size} articles) created recently, skipping")
            return -1
        }

        val briefingCount = articles.count { it.isSummary }
        val fidelityCount = articles.count { !it.isSummary }

        // Map articles to entities and determine feed names from article metadata.
        // Fallback to domain matching only when metadata is unavailable.
        val articleEntities = articles.mapIndexed { index, article ->
            val feedName = article.feedName.ifBlank {
                feeds.find { feed ->
                    val feedDomain = feed.url
                        .removePrefix("https://")
                        .removePrefix("http://")
                        .split("/")
                        .firstOrNull()
                        ?: ""
                    article.originalUrl.contains(feedDomain)
                }?.name ?: "Unknown"
            }

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

        // Get unique feed names only from articles that are actually in this digest
        val feedNames = articleEntities.map { it.feedName }.distinct().filter { it != "Unknown" }

        val digestEntity = DigestEntity(
            generatedAt = System.currentTimeMillis(),
            epubFilePath = epubFilePath,
            articleCount = articles.size,
            briefingCount = briefingCount,
            fidelityCount = fidelityCount,
            triggerType = triggerType,
            feedNames = feedNames.joinToString(","),
            period = period ?: if (triggerType == TriggerType.MANUAL) "manual" else null
        )

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

    /**
     * Delete all digests and their EPUB files.
     * Used for development/testing purposes.
     */
    suspend fun deleteAllDigests() {
        // Delete all EPUB files first
        val digests = digestDao.getAllDigestsList()
        digests.forEach { digest ->
            File(digest.epubFilePath).delete()
        }
        // Delete all from database (cascade will remove articles)
        digestDao.deleteAllDigests()
    }

    /**
     * Check if a digest with the given remote ID already exists.
     */
    suspend fun existsByRemoteId(remoteId: String): Boolean =
        digestDao.existsByRemoteId(remoteId)

    /**
     * Get all remote IDs of synced digests.
     */
    suspend fun getAllRemoteIds(): List<String> =
        digestDao.getAllRemoteIds()

    /**
     * Update the local EPUB path for an existing digest.
     */
    suspend fun updateDigestEpubPath(digestId: Long, epubFilePath: String) {
        digestDao.updateEpubFilePath(digestId, epubFilePath)
    }

    /**
     * Save a digest downloaded from Ghostwriter backend.
     * Now supports syncing individual article records for in-app display.
     *
     * @param remoteId The Ghostwriter digest ID (UUID)
     * @param epubFilePath The local path to the downloaded EPUB
     * @param articleCount Number of articles in the digest
     * @param generatedAt Timestamp when the digest was created
     * @param period The period (morning, noon, evening, manual)
     * @param articles Optional list of articles with content from Ghostwriter
     * @return The ID of the created digest
     */
    suspend fun saveRemoteDigest(
        remoteId: String,
        epubFilePath: String,
        articleCount: Int,
        generatedAt: Long,
        period: String,
        articles: List<DigestArticleResponse>? = null
    ): Long {
        // Check if this digest already exists (prevents race condition duplicates)
        if (existsByRemoteId(remoteId)) {
            Log.d("DigestRepository", "Digest with remoteId=$remoteId already exists, skipping")
            return -1
        }

        val triggerType = when (period.lowercase()) {
            "manual" -> TriggerType.MANUAL
            else -> TriggerType.SCHEDULED
        }

        // Extract feed names and counts from articles if available
        val feedNames = articles?.map { it.feedTitle }?.distinct() ?: emptyList()
        val briefingCount = articles?.count { it.mode == "summarized" } ?: 0
        val fidelityCount = articles?.count { it.mode == "raw" } ?: 0

        val digestEntity = DigestEntity(
            generatedAt = generatedAt,
            epubFilePath = epubFilePath,
            articleCount = articleCount,
            briefingCount = briefingCount,
            fidelityCount = fidelityCount,
            triggerType = triggerType,
            feedNames = feedNames.joinToString(","),
            remoteId = remoteId,
            period = period
        )

        val digestId = if (articles != null && articles.isNotEmpty()) {
            // Convert articles and insert with digest
            val articleEntities = articles.map { article ->
                DigestArticleEntity(
                    digestId = 0, // Will be set by transaction
                    title = article.title,
                    author = article.author ?: "",
                    content = article.content,
                    originalUrl = article.url,
                    isSummary = article.mode == "summarized",
                    feedName = article.feedTitle,
                    sortOrder = article.sortOrder
                )
            }
            digestDao.insertDigestWithArticles(digestEntity, articleEntities)
        } else {
            // No articles - insert digest only (backwards compatibility)
            digestDao.insertDigest(digestEntity)
        }

        // Cleanup old digests if we exceed the limit
        cleanupOldDigests()

        return digestId
    }
}
