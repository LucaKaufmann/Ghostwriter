package com.example.epilogue.data.local

import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.TriggerType
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DigestEntityTest {

    @Test
    fun `toDomain splits feed names and trims whitespace`() {
        val entity = DigestEntity(
            id = 42L,
            generatedAt = 1000L,
            epubFilePath = "/tmp/digest.epub",
            articleCount = 3,
            briefingCount = 1,
            fidelityCount = 2,
            triggerType = TriggerType.MANUAL,
            feedNames = "Feed One, Feed Two ,Feed Three",
            remoteId = "remote",
            period = "manual"
        )

        val domain = entity.toDomain()

        assertEquals(listOf("Feed One", "Feed Two", "Feed Three"), domain.feedNames)
        assertEquals(entity.id, domain.id)
        assertEquals(entity.epubFilePath, domain.epubFilePath)
        assertEquals(entity.triggerType, domain.triggerType)
    }

    @Test
    fun `toDomain returns empty feed list when blank`() {
        val entity = DigestEntity(
            id = 1L,
            generatedAt = 1000L,
            epubFilePath = "/tmp/digest.epub",
            articleCount = 0,
            briefingCount = 0,
            fidelityCount = 0,
            triggerType = TriggerType.SCHEDULED,
            feedNames = "",
            remoteId = null,
            period = null
        )

        val domain = entity.toDomain()

        assertTrue(domain.feedNames.isEmpty())
    }

    @Test
    fun `fromDomain joins feed names`() {
        val digest = Digest(
            id = 3L,
            generatedAt = 2000L,
            epubFilePath = "/tmp/digest.epub",
            articleCount = 2,
            briefingCount = 1,
            fidelityCount = 1,
            triggerType = TriggerType.SCHEDULED,
            feedNames = listOf("Feed A", "Feed B"),
            remoteId = "remote",
            period = "evening"
        )

        val entity = DigestEntity.fromDomain(digest)

        assertEquals("Feed A,Feed B", entity.feedNames)
        assertEquals(digest.id, entity.id)
        assertEquals(digest.remoteId, entity.remoteId)
        assertEquals(digest.period, entity.period)
    }
}
