package com.example.epilogue.data.repository

import com.example.epilogue.data.local.DigestArticleEntity
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.DigestEntity
import com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.domain.model.TriggerType
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class DigestRepositoryTest {

    private val digestDao: DigestDao = mockk(relaxed = true)
    private val repository = DigestRepository(digestDao)

    @Test
    fun `saveDigest returns -1 when recent digest exists`() = runTest {
        coEvery { digestDao.existsRecentDigest(any(), any()) } returns true

        val result = repository.saveDigest(
            articles = listOf(sampleArticle("A", false)),
            feeds = emptyList(),
            epubFilePath = "/tmp/digest.epub",
            triggerType = TriggerType.MANUAL
        )

        assertEquals(-1L, result)
        coVerify(exactly = 0) { digestDao.insertDigestWithArticles(any(), any()) }
    }

    @Test
    fun `saveDigest maps feed names and counts`() = runTest {
        val digestSlot = slot<DigestEntity>()
        val articleSlot = slot<List<DigestArticleEntity>>()

        coEvery { digestDao.existsRecentDigest(any(), any()) } returns false
        coEvery { digestDao.insertDigestWithArticles(capture(digestSlot), capture(articleSlot)) } returns 11L
        coEvery { digestDao.getDigestCount() } returns 0

        val feeds = listOf(
            Feed(
                url = "https://example.com/rss",
                name = "Example",
                mode = ProcessingMode.FIDELITY
            )
        )
        val articles = listOf(
            sampleArticle("Matched", true, "https://example.com/story"),
            sampleArticle("Unknown", false, "https://unknown.com/story")
        )

        val result = repository.saveDigest(
            articles = articles,
            feeds = feeds,
            epubFilePath = "/tmp/digest.epub",
            triggerType = TriggerType.MANUAL
        )

        assertEquals(11L, result)
        assertEquals(2, digestSlot.captured.articleCount)
        assertEquals(1, digestSlot.captured.briefingCount)
        assertEquals(1, digestSlot.captured.fidelityCount)
        assertEquals("Example", digestSlot.captured.feedNames)
        assertEquals("manual", digestSlot.captured.period)

        assertEquals(2, articleSlot.captured.size)
        assertEquals("Example", articleSlot.captured[0].feedName)
        assertEquals("Unknown", articleSlot.captured[1].feedName)
    }

    @Test
    fun `saveRemoteDigest returns -1 when remote id exists`() = runTest {
        coEvery { digestDao.existsByRemoteId("remote") } returns true

        val result = repository.saveRemoteDigest(
            remoteId = "remote",
            epubFilePath = "/tmp/digest.epub",
            articleCount = 2,
            generatedAt = 1000L,
            period = "morning",
            articles = emptyList()
        )

        assertEquals(-1L, result)
        coVerify(exactly = 0) { digestDao.insertDigest(any()) }
        coVerify(exactly = 0) { digestDao.insertDigestWithArticles(any(), any()) }
    }

    @Test
    fun `saveRemoteDigest inserts articles and counts`() = runTest {
        val digestSlot = slot<DigestEntity>()
        val articleSlot = slot<List<DigestArticleEntity>>()

        coEvery { digestDao.existsByRemoteId("remote") } returns false
        coEvery { digestDao.insertDigestWithArticles(capture(digestSlot), capture(articleSlot)) } returns 22L
        coEvery { digestDao.getDigestCount() } returns 0

        val articles = listOf(
            DigestArticleResponse(
                id = "1",
                title = "Summary",
                url = "https://example.com/summary",
                mode = "summarized",
                wordCount = 100,
                content = "Summary content",
                author = "Author",
                feedTitle = "Feed",
                sortOrder = 1,
                aiFailed = false
            ),
            DigestArticleResponse(
                id = "2",
                title = "Full",
                url = "https://example.com/full",
                mode = "raw",
                wordCount = 200,
                content = "Full content",
                author = null,
                feedTitle = "Feed",
                sortOrder = 2,
                aiFailed = false
            )
        )

        val result = repository.saveRemoteDigest(
            remoteId = "remote",
            epubFilePath = "/tmp/digest.epub",
            articleCount = 2,
            generatedAt = 1000L,
            period = "morning",
            articles = articles
        )

        assertEquals(22L, result)
        assertEquals(1, digestSlot.captured.briefingCount)
        assertEquals(1, digestSlot.captured.fidelityCount)
        assertEquals(TriggerType.SCHEDULED, digestSlot.captured.triggerType)
        assertEquals(2, articleSlot.captured.size)
        assertTrue(articleSlot.captured[0].isSummary)
        assertFalse(articleSlot.captured[1].isSummary)
    }

    @Test
    fun `deleteDigest removes file and deletes record`() = runTest {
        val tempFile = File.createTempFile("digest", ".epub")
        assertTrue(tempFile.exists())

        val digest = Digest(
            id = 55L,
            generatedAt = 1000L,
            epubFilePath = tempFile.absolutePath,
            articleCount = 1,
            briefingCount = 1,
            fidelityCount = 0,
            triggerType = TriggerType.MANUAL,
            feedNames = emptyList(),
            remoteId = null,
            period = "manual"
        )

        val result = repository.deleteDigest(digest)

        assertTrue(result)
        assertFalse(tempFile.exists())
        coVerify { digestDao.deleteDigestById(55L) }
    }

    private fun sampleArticle(title: String, isSummary: Boolean, url: String = "https://example.com/$title"): ProcessedArticle {
        return ProcessedArticle(
            title = title,
            author = "Author",
            content = "<p>Content</p>",
            originalUrl = url,
            isSummary = isSummary
        )
    }
}
