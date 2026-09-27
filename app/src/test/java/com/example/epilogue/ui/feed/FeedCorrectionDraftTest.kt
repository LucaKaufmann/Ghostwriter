package com.example.epilogue.ui.feed

import com.example.epilogue.data.local.FeedMutationEntity
import com.example.epilogue.domain.model.ProcessingMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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
        val draft = requireNotNull(correctionDraft(rejected("""{"title":"Corrected"}""")))
        assertEquals("Corrected", draft.title)
        assertEquals(ProcessingMode.BRIEFING, draft.mode)
        assertFalse(draft.enabled)
        assertEquals(20, draft.maxArticles)
    }

    @Test fun `sparse rejected head without a complete base cannot inherit successor values`() {
        assertNull(correctionDraft(rejected("""{"title":"Corrected"}""", null)))
    }

    @Test fun `absent create with complete head payload remains correctable`() {
        val draft = requireNotNull(correctionDraft(rejected(
            """{"title":"New","mode":"raw","is_active":true,"max_articles":5}""", null)))
        assertEquals("New", draft.title)
        assertEquals(ProcessingMode.FIDELITY, draft.mode)
        assertTrue(draft.enabled)
        assertEquals(5, draft.maxArticles)
    }

    @Test fun `rejected invalid title and cap remain editable`() {
        val draft = requireNotNull(correctionDraft(rejected(
            """{"title":"","max_articles":-1}""")))
        assertEquals("", draft.title)
        assertEquals(-1, draft.maxArticles)
        assertEquals(ProcessingMode.BRIEFING, draft.mode)
        assertFalse(draft.enabled)
    }

    @Test fun `server refresh updates untouched defaults without replacing typed edits`() {
        val fields = """{"title":"Rejected"}"""
        val initial = requireNotNull(correctionDraft(rejected(fields,
            """{"kind":"feed","title":"Server","mode":"raw","is_active":true,"max_articles":0}""")))
        val typed = correctionForm(initial, "Corrected", null, null, null)
        assertEquals("Corrected", typed.title)
        assertEquals(ProcessingMode.FIDELITY, typed.mode)
        assertTrue(typed.enabled)

        val refreshed = requireNotNull(correctionDraft(rejected(fields,
            """{"kind":"feed","title":"Server","mode":"summarize","is_active":false,"max_articles":7}""")))
        val afterPull = correctionForm(refreshed, "Corrected", null, null, null)
        assertEquals("Corrected", afterPull.title)
        assertEquals("7", afterPull.cap)
        assertEquals(ProcessingMode.BRIEFING, afterPull.mode)
        assertFalse(afterPull.enabled)
        val intentional = correctionForm(refreshed, "Corrected", "2", false, true)
        assertEquals("2", intentional.cap)
        assertEquals(ProcessingMode.FIDELITY, intentional.mode)
        assertTrue(intentional.enabled)
    }
}
