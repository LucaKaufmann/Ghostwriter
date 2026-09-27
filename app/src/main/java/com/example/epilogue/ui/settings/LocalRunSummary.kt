package com.example.epilogue.ui.settings

import com.example.epilogue.data.local.GenerationRunEntity
import org.json.JSONObject

/** Safe, persisted local-generation status. No article content or feed credentials enter UI. */
data class LocalRunSummary(val title: String, val counts: String, val reasons: String?) {
    companion object {
        fun from(row: GenerationRunEntity): LocalRunSummary {
            val json = runCatching { JSONObject(row.diagnosticsJson) }.getOrDefault(JSONObject())
            val title = when (row.outcome) {
                "complete" -> "Complete"
                "partial" -> "Partial"
                "empty" -> "Empty"
                "deferred" -> "Deferred"
                "failed" -> "Failed"
                "cancelled" -> "Cancelled"
                else -> "Finished"
            }
            val counts = "Delivered ${json.optInt("delivered_count")} · " +
                "Filtered ${json.optInt("filtered_count")} · " +
                "Waiting ${json.optInt("cap_deferred_count")} · " +
                "Failed ${json.optInt("failed_count")}"
            val reasons = json.optJSONObject("reason_counts")
                ?.let { countsObject ->
                    countsObject.keys().asSequence().toList().sorted().mapNotNull { key ->
                        val label = reasonLabel(key) ?: return@mapNotNull null
                        val count = countsObject.optInt(key)
                        if (count > 0) "$label ($count)" else null
                    }.joinToString(" · ").ifBlank { null }
                } ?: reasonLabel(json.optString("code"))
            return LocalRunSummary("Last local run: $title", counts, reasons)
        }

        private fun reasonLabel(code: String): String? = when (code) {
            "promotional" -> "Promotional content"
            "model_promotional" -> "Model marked promotional"
            "content_too_short" -> "Below minimum word count"
            "invalid_identity" -> "Invalid article link"
            "fetch_failed" -> "Feed fetch failed"
            "extract_failed", "process_failed" -> "Article extraction failed"
            "full_article_fallback" -> "Summary unavailable; full article kept"
            "epub_failed" -> "EPUB creation failed"
            "claim_conflict" -> "Delivery changed during generation"
            "generation_failed" -> "Generation failed"
            else -> null
        }
    }
}
