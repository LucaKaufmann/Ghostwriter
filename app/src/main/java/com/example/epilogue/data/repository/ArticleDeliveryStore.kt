package com.example.epilogue.data.repository

import androidx.room.withTransaction
import com.example.epilogue.data.local.ArticleDeliveryDao
import com.example.epilogue.data.local.ArticleDeliveryEntity
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.local.GenerationRunDao
import com.example.epilogue.data.local.GenerationRunEntity
import javax.inject.Inject
import javax.inject.Singleton

class DeliveryClaimConflict : IllegalStateException("Article was delivered by another run")

@Singleton
class ArticleDeliveryStore @Inject constructor(
    private val database: EpilogueDatabase,
    private val deliveries: ArticleDeliveryDao,
    private val runs: GenerationRunDao
) {
    suspend fun startRun(regeneration: Boolean): Long = runs.insert(GenerationRunEntity(
        startedAt = System.currentTimeMillis(), regeneration = regeneration))

    suspend fun forFeed(feedUrl: String): Map<String, ArticleDeliveryEntity> =
        deliveries.forFeed(feedUrl).associateBy { it.articleKey }

    /** Attempt markers survive failure/cancellation but are never terminal claims. */
    suspend fun markAttempts(runId: Long, identities: List<DeliveryIdentity>,
        signature: String, regeneration: Boolean) = database.withTransaction {
        for (identity in identities) {
            val old = deliveries.get(identity.feedUrl, identity.articleKey)
            if (old?.state == "delivered") {
                if (!regeneration) throw DeliveryClaimConflict()
                continue
            }
            if (old?.state == "excluded" && old.filterSignature == signature && !regeneration)
                throw DeliveryClaimConflict()
            deliveries.put((old ?: ArticleDeliveryEntity(identity.feedUrl, identity.articleKey,
                "retryable")).copy(lastAttemptSequence = runId))
        }
    }

    suspend fun finishWithoutDigest(runId: Long, outcome: String, diagnosticsJson: String,
        exclusions: List<ExcludedArticle> = emptyList()) =
        database.withTransaction {
            if (runs.get(runId)?.outcome != "running") return@withTransaction
            if (outcome in setOf("empty", "deferred")) {
                for (excluded in exclusions) {
                    val old = deliveries.get(excluded.identity.feedUrl, excluded.identity.articleKey)
                    if (old?.state == "delivered") continue
                    deliveries.put((old ?: ArticleDeliveryEntity(excluded.identity.feedUrl,
                        excluded.identity.articleKey, "retryable")).copy(
                        state = "excluded", reason = excluded.reason,
                        filterSignature = excluded.signature,
                        committedAt = System.currentTimeMillis()))
                }
            }
            runs.finish(runId, System.currentTimeMillis(), outcome, null, diagnosticsJson)
        }
}
