package com.example.epilogue.data.repository

import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import org.json.JSONArray
import org.json.JSONObject

data class DeliveryIdentity(val feedUrl: String, val articleKey: String)
data class DeliveredArticle(val identity: DeliveryIdentity, val article: ProcessedArticle,
    val filterSignature: String)
data class ExcludedArticle(val identity: DeliveryIdentity, val reason: String, val signature: String)
data class DeliveryIssue(val articleKey: String?, val stage: String, val code: String)

data class FeedIngestionResult(
    val feed: Feed,
    val candidateCount: Int,
    val selectedCount: Int,
    val delivered: List<DeliveredArticle>,
    val excluded: List<ExcludedArticle>,
    val failedItems: List<DeliveryIssue>,
    val capDeferredCount: Int,
    val feedError: String? = null,
    val fallbackCount: Int = 0
) {
    val deliveredCount get() = delivered.size
    val filteredCount get() = excluded.size
}

data class GenerationDiagnostics(val feeds: List<FeedIngestionResult>) {
    val articles get() = feeds.flatMap { it.delivered }
    val exclusions get() = feeds.flatMap { it.excluded }
    val failures get() = feeds.sumOf { it.failedItems.size + if (it.feedError == null) 0 else 1 }
    val capDeferred get() = feeds.sumOf { it.capDeferredCount }
    val fallbackCount get() = feeds.sumOf { it.fallbackCount }
    val selected get() = feeds.sumOf { it.selectedCount }
    val outcome: String get() = when {
        articles.isNotEmpty() && failures == 0 && capDeferred == 0 && fallbackCount == 0 -> "complete"
        articles.isNotEmpty() -> "partial"
        failures > 0 -> "failed"
        exclusions.isNotEmpty() && capDeferred > 0 -> "deferred"
        else -> "empty"
    }

    fun toJson(): String = JSONObject()
        .put("outcome", outcome)
        .put("selected_count", selected)
        .put("delivered_count", articles.size)
        .put("filtered_count", exclusions.size)
        .put("cap_deferred_count", capDeferred)
        .put("fallback_count", fallbackCount)
        .put("failed_count", failures)
        .put("reason_counts", JSONObject().also { counts ->
            val reasons = feeds.flatMap { feed ->
                feed.excluded.map { it.reason } + feed.failedItems.map { it.code } +
                    listOfNotNull(feed.feedError)
            }.groupingBy { it }.eachCount()
            reasons.forEach { (reason, count) -> counts.put(reason, count) }
        })
        .put("feeds", JSONArray(feeds.map { feed -> JSONObject()
            .put("candidate_count", feed.candidateCount)
            .put("selected_count", feed.selectedCount)
            .put("delivered_count", feed.deliveredCount)
            .put("filtered_count", feed.filteredCount)
            .put("cap_deferred_count", feed.capDeferredCount)
            .put("feed_error", feed.feedError)
            .put("failed_items", JSONArray(feed.failedItems.map { issue -> JSONObject()
                .put("article_key", issue.articleKey)
                .put("stage", issue.stage)
                .put("code", issue.code)
            }))
        }))
        .toString()
}
