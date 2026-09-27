package com.example.epilogue.ui.settings

import com.example.epilogue.data.local.GenerationRunEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class LocalRunSummaryTest {
    private fun row(outcome: String, json: String) = GenerationRunEntity(
        runId = 7, startedAt = 1, finishedAt = 2, outcome = outcome,
        diagnosticsJson = json)

    @Test fun `partial displays durable counts and safe fallback and failure reasons`() {
        val summary = LocalRunSummary.from(row("partial", """
            {"delivered_count":2,"filtered_count":1,"cap_deferred_count":3,"failed_count":1,
             "reason_counts":{"full_article_fallback":1,"fetch_failed":1,"promotional":1}}
        """))
        assertEquals("Last local run: Partial", summary.title)
        assertEquals("Delivered 2 · Filtered 1 · Waiting 3 · Failed 1", summary.counts)
        assertTrue(summary.reasons!!.contains("Feed fetch failed"))
        assertTrue(summary.reasons!!.contains("Summary unavailable; full article kept"))
    }

    @Test fun `empty deferred and failed retain useful status without promising an EPUB`() {
        val empty = LocalRunSummary.from(row("empty",
            """{"delivered_count":0,"filtered_count":1,"reason_counts":{"model_promotional":1}}"""))
        val deferred = LocalRunSummary.from(row("deferred",
            """{"delivered_count":0,"filtered_count":2,"cap_deferred_count":3,
                "reason_counts":{"content_too_short":2}}"""))
        val failed = LocalRunSummary.from(row("failed",
            """{"outcome":"failed","code":"epub_failed"}"""))
        assertEquals("Last local run: Empty", empty.title)
        assertTrue(empty.reasons!!.contains("Model marked promotional"))
        assertEquals("Last local run: Deferred", deferred.title)
        assertTrue(deferred.counts.contains("Waiting 3"))
        assertTrue(deferred.reasons!!.contains("Below minimum word count"))
        assertEquals("Last local run: Failed", failed.title)
        assertEquals("EPUB creation failed", failed.reasons)
        assertFalse(listOf(empty, deferred, failed).any { it.title.contains("Open") })
    }

    @Test fun `unknown diagnostic text is not rendered into Settings`() {
        val summary = LocalRunSummary.from(row("failed",
            """{"code":"https://secret.example/?token=private","reason_counts":{"secret":1}}"""))
        assertEquals(null, summary.reasons)
    }
}
