package com.example.epilogue.data.repository

import android.util.Log
import com.example.epilogue.data.local.DigestArticleEntity
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.DigestEntity
import com.example.epilogue.data.local.ArticleDeliveryDao
import com.example.epilogue.data.local.ArticleDeliveryEntity
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.local.GenerationRunDao
import androidx.room.withTransaction
import com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.DigestArticle
import com.example.epilogue.domain.model.DigestPeriod
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.TriggerType
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for managing digest history.
 */
@Singleton
class DigestRepository @Inject constructor(
    private val digestDao: DigestDao,
    private val database: EpilogueDatabase,
    private val deliveries: ArticleDeliveryDao,
    private val runs: GenerationRunDao
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
     * Create a digest placeholder while generation is in progress.
     */
    suspend fun createPendingDigest(
        feeds: List<Feed>,
        triggerType: TriggerType,
        period: String? = null
    ): Long {
        val feedNames = feeds.map { it.name }.distinct()
        val digestEntity = DigestEntity(
            generatedAt = System.currentTimeMillis(),
            epubFilePath = "",
            articleCount = 0,
            briefingCount = 0,
            fidelityCount = 0,
            triggerType = triggerType,
            feedNames = feedNames.joinToString(","),
            period = period ?: if (triggerType == TriggerType.MANUAL) "manual" else null,
            isComplete = false,
            errorMessage = null
        )
        return digestDao.insertDigest(digestEntity)
    }

    /**
     * Finalize an in-progress digest with generated content.
     */
    suspend fun completePendingDigest(
        digestId: Long,
        articles: List<ProcessedArticle>,
        feeds: List<Feed>,
        epubFilePath: String
    ) {
        val briefingCount = articles.count { it.isSummary }
        val fidelityCount = articles.count { !it.isSummary }

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
                digestId = digestId,
                title = article.title,
                author = article.author,
                content = article.content,
                originalUrl = article.originalUrl,
                isSummary = article.isSummary,
                feedName = feedName,
                sortOrder = index,
                feedUrl = article.feedUrl.takeIf { it.isNotBlank() }
            )
        }

        val feedNames = articleEntities.map { it.feedName }.distinct().filter { it != "Unknown" }

        digestDao.completeDigestWithArticles(
            digestId = digestId,
            epubFilePath = epubFilePath,
            articleCount = articles.size,
            briefingCount = briefingCount,
            fidelityCount = fidelityCount,
            feedNames = feedNames.joinToString(","),
            articles = articleEntities
        )

        cleanupOldDigests()
    }

    /** An EPUB has already been durably written before this transaction starts. */
    suspend fun finalizeDeliveryRun(
        runId: Long, diagnostics: GenerationDiagnostics,
        epubFilePath: String, triggerType: TriggerType, period: String?,
        regeneration: Boolean
    ): Long {
        require(diagnostics.articles.isNotEmpty() && diagnostics.outcome in setOf("complete", "partial"))
        val articles = diagnostics.articles
        val digestId = database.withTransaction {
            check(runs.get(runId)?.outcome == "running")
            val feedNames = articles.map { it.article.feedName }.distinct()
            val digest = DigestEntity(
                generatedAt = System.currentTimeMillis(), epubFilePath = epubFilePath,
                articleCount = articles.size,
                briefingCount = articles.count { it.article.isSummary },
                fidelityCount = articles.count { !it.article.isSummary },
                triggerType = triggerType, feedNames = feedNames.joinToString(","),
                period = period, isComplete = true
            )
            val id = digestDao.insertDigest(digest)
            digestDao.insertArticles(articles.mapIndexed { index, delivered ->
                val article = delivered.article
                DigestArticleEntity(
                    digestId = id, title = article.title, author = article.author,
                    content = article.content, originalUrl = article.originalUrl,
                    isSummary = article.isSummary, feedName = article.feedName,
                    sortOrder = index, feedUrl = delivered.identity.feedUrl)
            })
            for (delivered in articles) {
                val key = delivered.identity
                val old = deliveries.get(key.feedUrl, key.articleKey)
                if (old?.state == "delivered") {
                    if (!regeneration) throw DeliveryClaimConflict()
                    continue // Regeneration never rewrites an earlier first-delivery claim.
                }
                if (old?.state == "excluded" && !regeneration &&
                    old.filterSignature == delivered.filterSignature) {
                    throw DeliveryClaimConflict()
                }
                deliveries.put((old ?: ArticleDeliveryEntity(key.feedUrl, key.articleKey,
                    "retryable")).copy(state = "delivered", reason = null,
                    filterSignature = null, firstDigestId = id,
                    committedAt = System.currentTimeMillis()))
            }
            for (excluded in diagnostics.exclusions) {
                val key = excluded.identity
                val old = deliveries.get(key.feedUrl, key.articleKey)
                if (old?.state == "delivered") continue
                deliveries.put((old ?: ArticleDeliveryEntity(key.feedUrl, key.articleKey,
                    "retryable")).copy(state = "excluded", reason = excluded.reason,
                    filterSignature = excluded.signature,
                    committedAt = System.currentTimeMillis()))
            }
            runs.finish(runId, System.currentTimeMillis(), diagnostics.outcome, id,
                diagnostics.toJson())
            id
        }
        // Retention is post-commit maintenance; it must not demote a completed digest.
        try { cleanupOldDigests() } catch (failure: Exception) {
            Log.w("DigestRepository", "Could not clean old digests", failure)
        }
        return digestId
    }

    /** Keep a newly generated EPUB owned until its history finalization succeeds. */
    suspend fun <T> withGeneratedArtifact(file: File, action: suspend () -> T): T {
        var completed = false
        try {
            val result = action()
            completed = true
            return result
        } finally {
            if (!completed) {
                // Cancellation must not interrupt the reference check and cleanup.
                // A finalization failure may occur after the history row was committed.
                withContext(NonCancellable) {
                    try {
                        digestDao.removeUnreferencedArtifact(file.absolutePath, ::removeArtifact)
                    } catch (failure: Exception) {
                        Log.w("DigestRepository", "Could not clean generated EPUB", failure)
                    }
                }
            }
        }
    }

    suspend fun markDigestFailed(digestId: Long, errorMessage: String) {
        digestDao.markDigestFailed(digestId, errorMessage)
    }

    suspend fun deleteDigestById(digestId: Long) {
        digestDao.deleteWithArtifact(digestId, ::removeArtifact)
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
                sortOrder = index,
                feedUrl = article.feedUrl.takeIf { it.isNotBlank() }
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
            period = period ?: if (triggerType == TriggerType.MANUAL) "manual" else null,
            isComplete = true,
            errorMessage = null
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
        // Re-read the persisted path: the caller may hold an older UI snapshot.
        return digestDao.deleteWithArtifact(digest.id, ::removeArtifact)
    }

    private fun removeArtifact(path: String): Boolean {
        val file = File(path)
        return !file.exists() || (file.isFile && file.delete())
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
                digestDao.deleteWithArtifact(digest.id, ::removeArtifact)
            }
        }
    }

    /**
     * Delete all digests and their EPUB files.
     * Used for development/testing purposes.
     */
    suspend fun deleteAllDigests(): Boolean {
        // The action clears a snapshot of current history. Concurrently created
        // editions remain, and completed per-row deletions cannot be rolled back as a batch.
        return digestDao.deleteAllWithArtifacts(::removeArtifact)
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
     * Returns the timestamp of the most recent locally scheduled digest for the given period.
     */
    suspend fun getLatestScheduledDigestTimeForPeriod(period: DigestPeriod): Long? {
        return digestDao.getLatestDigestTimestampForPeriod(
            triggerType = TriggerType.SCHEDULED,
            period = period.name.lowercase()
        )
    }

    /**
     * Delete stale local EPUB files for Ghostwriter-synced digests while keeping digest metadata.
     *
     * @param retentionMillis Keep files modified within this retention window.
     * @return Number of files deleted.
     */
    suspend fun cleanupStaleRemoteEpubFiles(retentionMillis: Long): Int {
        val cutoff = System.currentTimeMillis() - retentionMillis
        var deletedCount = 0

        digestDao.getRemoteDigests().forEach { digest ->
            val path = digest.epubFilePath
            if (path.isBlank()) return@forEach

            val file = File(path)
            if (!file.exists()) return@forEach

            if (file.lastModified() < cutoff) {
                if (digestDao.removeUnsharedArtifact(digest.id) { currentPath ->
                    val currentFile = File(currentPath)
                    currentFile.isFile && currentFile.lastModified() < cutoff && currentFile.delete()
                }) {
                    deletedCount++
                }
            }
        }

        return deletedCount
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
        val briefingCount = articles?.count {
            it.mode == "summarize" || it.mode == "summarized"
        } ?: 0
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
            period = period,
            isComplete = true,
            errorMessage = null
        )

        val digestId = if (articles != null && articles.isNotEmpty()) {
            // Convert articles and insert with digest
            val articleEntities = articles.map { article ->
                DigestArticleEntity(
                    digestId = 0, // Will be set by transaction
                    title = article.title,
                    author = article.author ?: "",
                    content = article.contentHtml?.takeIf { it.isNotBlank() } ?: article.content,
                    originalUrl = article.url,
                    isSummary = article.mode == "summarize" || article.mode == "summarized",
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
