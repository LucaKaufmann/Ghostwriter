package com.example.epilogue.ui.feed

import com.example.epilogue.data.local.FeedMutationEntity
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class FeedCorrectionDraftTest {
    private val url = "https://example.test/feed"
    private val server = """{"kind":"feed","title":"Server","mode":"summarize","is_active":false,"max_articles":20}"""

    private fun rejected(fields: String, snapshot: String? = server) = FeedMutationEntity(
        opId = "proposal", serverKey = "scope", url = url, kind = "upsert", baseVersion = 1,
        fieldsJson = fields, localRevision = 1, state = "rejected",
        serverSnapshotJson = snapshot, createdAt = 1, sequence = 1, queueOrder = 1)

    @Test fun `title only correction keeps server mode enabled state and cap`() {
        val draft = correctionDraft(rejected("""{"title":"Corrected"}"""), null)
        assertEquals("Corrected", draft.title)
        assertEquals(ProcessingMode.BRIEFING, draft.mode)
        assertFalse(draft.enabled)
        assertEquals(20, draft.maxArticles)
    }

    @Test fun `cap only correction obtains complete title from current feed`() {
        val current = Feed(url, "Local title", ProcessingMode.BRIEFING,
            maxArticles = 20, isEnabled = false)
        val draft = correctionDraft(rejected("""{"max_articles":5}""", null), current)
        assertEquals("Local title", draft.title)
        assertEquals(ProcessingMode.BRIEFING, draft.mode)
        assertFalse(draft.enabled)
        assertEquals(5, draft.maxArticles)
    }
}
