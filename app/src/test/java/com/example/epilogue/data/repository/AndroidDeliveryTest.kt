package com.example.epilogue.data.repository

import androidx.room.Room
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.domain.model.TriggerType
import com.example.epilogue.service.ContentProcessor
import com.example.epilogue.service.OpenAIService
import com.example.epilogue.service.PromotionalContentFilter
import com.example.epilogue.service.RssService
import com.example.epilogue.service.GenerationGate
import com.example.epilogue.shared.delivery.ArticleDeliveryIdentity
import com.example.epilogue.shared.delivery.ArticleIdentityResult
import com.prof18.rssparser.model.RssItem
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.yield
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class AndroidDeliveryTest {
    @get:Rule val files = TemporaryFolder()
    private lateinit var db: EpilogueDatabase
    private lateinit var ledger: ArticleDeliveryStore
    private lateinit var digests: DigestRepository
    private val feed = Feed("https://example.test/feed", "Fixture", ProcessingMode.FIDELITY,
        maxArticles = 2)

    @Before fun setUp() {
        db = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), EpilogueDatabase::class.java)
            .allowMainThreadQueries().build()
        ledger = ArticleDeliveryStore(db, db.articleDeliveryDao(), db.generationRunDao())
        digests = DigestRepository(db.digestDao(), db, db.articleDeliveryDao(), db.generationRunDao())
    }

    @After fun tearDown() { db.close() }

    private fun article(n: Int) = ProcessedArticle(
        "Article $n", "Author", "<p>Body $n</p>", "https://example.test/articles/$n", false,
        feedUrl = feed.url, feedName = feed.name)
    private fun key(n: Int) = DeliveryIdentity(feed.url,
        (ArticleDeliveryIdentity().fromArticleLink(article(n).originalUrl) as ArticleIdentityResult.Valid).articleKey)
    private fun result(n: Int, signature: String = "filter-a") =
        DeliveredArticle(key(n), article(n), signature)
    private fun diagnostics(vararg articles: DeliveredArticle) = GenerationDiagnostics(listOf(
        FeedIngestionResult(feed, articles.size, articles.size, articles.toList(), emptyList(),
            emptyList(), 0)))
    private suspend fun commit(run: Long, n: Int, file: File, signature: String = "filter-a",
        regeneration: Boolean = false): Long =
        digests.withGeneratedArtifact(file) {
            digests.finalizeDeliveryRun(run, diagnostics(result(n, signature)),
                file.absolutePath, TriggerType.MANUAL, "manual", regeneration)
        }

    @Test fun `claim history association and run commit together and survive history deletion`() = runBlocking {
        val run = ledger.startRun(false)
        ledger.markAttempts(run, listOf(key(1)), "filter-a", false)
        val file = files.newFile("delivered.epub").apply { writeText("synthetic") }
        val digestId = commit(run, 1, file)
        assertEquals("delivered", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        assertEquals(digestId, db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.firstDigestId)
        assertEquals(feed.url, db.digestDao().getArticlesForDigest(digestId).single().feedUrl)
        assertEquals("complete", db.generationRunDao().get(run)?.outcome)
        assertEquals(digestId, db.generationRunDao().get(run)?.digestId)
        digests.deleteDigestById(digestId)
        assertFalse(file.exists())
        assertEquals("delivered", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
    }

    @Test fun `transaction failure rolls back claim history and associations while keeping attempt`() = runBlocking {
        val run = ledger.startRun(false)
        ledger.markAttempts(run, listOf(key(1)), "filter-a", false)
        db.openHelper.writableDatabase.execSQL(
            "CREATE TRIGGER fail_association BEFORE INSERT ON digest_articles " +
                "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        val file = files.newFile("rollback.epub")
        assertNotNull(runCatching { commit(run, 1, file) }.exceptionOrNull())
        assertFalse(file.exists())
        assertEquals(0, db.digestDao().getDigestCount())
        assertEquals("retryable", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        assertEquals("running", db.generationRunDao().get(run)?.outcome)
    }

    @Test fun `duplicate claim loses atomically and regeneration preserves first claim`() = runBlocking {
        val first = ledger.startRun(false)
        val firstId = commit(first, 1, files.newFile("first.epub"))
        val second = ledger.startRun(false)
        val duplicate = files.newFile("duplicate.epub")
        assertTrue(runCatching { commit(second, 1, duplicate) }.exceptionOrNull() is DeliveryClaimConflict)
        assertFalse(duplicate.exists())
        assertEquals(1, db.digestDao().getDigestCount())
        val regenerated = ledger.startRun(true)
        val newId = commit(regenerated, 1, files.newFile("regen.epub"), regeneration = true)
        assertNotEquals(firstId, newId)
        assertEquals(firstId, db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.firstDigestId)
        assertEquals(2, db.digestDao().getDigestCount())
        ledger.finishWithoutDigest(regenerated, "failed", "{}")
        assertEquals("complete", db.generationRunDao().get(regenerated)?.outcome)
    }

    @Test fun `cancel and failure keep attempts retryable and never commit exclusions`() = runBlocking {
        val run = ledger.startRun(false)
        ledger.markAttempts(run, listOf(key(1)), "filter-a", false)
        val exclusion = ExcludedArticle(key(1), "content_too_short", "filter-a")
        ledger.finishWithoutDigest(run, "cancelled", "{}", listOf(exclusion))
        assertEquals("retryable", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        ledger.finishWithoutDigest(run, "deferred", "{}", listOf(exclusion))
        assertEquals("cancelled", db.generationRunDao().get(run)?.outcome)
        val next = ledger.startRun(false)
        ledger.markAttempts(next, listOf(key(1)), "filter-a", false)
        ledger.finishWithoutDigest(next, "empty", "{}", listOf(exclusion))
        assertEquals("excluded", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        assertNotNull(db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.committedAt)
        val changed = ledger.startRun(false)
        ledger.markAttempts(changed, listOf(key(1)), "filter-b", false)
        assertEquals(changed, db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.lastAttemptSequence)
    }

    @Test fun `postcommit cancellation keeps referenced EPUB and completed run`() = runBlocking {
        val run = ledger.startRun(false)
        val file = files.newFile("postcommit.epub").apply { writeText("synthetic") }
        assertTrue(runCatching {
            digests.withGeneratedArtifact(file) {
                digests.finalizeDeliveryRun(run, diagnostics(result(1)),
                    file.absolutePath, TriggerType.MANUAL, "manual", false)
                throw CancellationException("after commit")
            }
        }.exceptionOrNull() is CancellationException)
        ledger.finishWithoutDigest(run, "cancelled", "{}")
        assertTrue(file.exists())
        assertEquals("complete", db.generationRunDao().get(run)?.outcome)
    }

    @Test fun `filtered only completion records exclusion while failed run does not`() = runBlocking {
        val excluded = ExcludedArticle(key(1), "promotional", "filter-a")
        val filtered = GenerationDiagnostics(listOf(FeedIngestionResult(feed, 1, 1,
            emptyList(), listOf(excluded), emptyList(), 0)))
        assertEquals("empty", filtered.outcome)
        val failed = ledger.startRun(false)
        ledger.markAttempts(failed, listOf(key(1)), "filter-a", false)
        ledger.finishWithoutDigest(failed, "failed", filtered.toJson(), filtered.exclusions)
        assertEquals("retryable", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        val completed = ledger.startRun(false)
        ledger.markAttempts(completed, listOf(key(1)), "filter-a", false)
        ledger.finishWithoutDigest(completed, filtered.outcome, filtered.toJson(), filtered.exclusions)
        assertEquals("excluded", db.articleDeliveryDao().get(feed.url, key(1).articleKey)?.state)
        assertEquals("empty", db.generationRunDao().get(completed)?.outcome)
        assertTrue(db.generationRunDao().get(completed)!!.diagnosticsJson.contains("filtered_count"))
        val deferred = GenerationDiagnostics(listOf(FeedIngestionResult(feed, 3, 1,
            emptyList(), listOf(excluded), emptyList(), 2)))
        assertEquals("deferred", deferred.outcome)
    }

    @Test fun `process wide gate serializes concurrent generation entries`() = runBlocking {
        val gate = GenerationGate()
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        var secondEntered = false
        val first = async { gate.run { entered.complete(Unit); release.await() } }
        entered.await()
        val second = async { gate.run { secondEntered = true } }
        yield()
        assertFalse(secondEntered)
        release.complete(Unit)
        first.await()
        second.await()
        assertTrue(secondEntered)
    }

    @Test fun `five candidates cap two rotates never attempted ahead of failed first item`() = runBlocking {
        val rss = mockk<RssService>()
        val processor = mockk<ContentProcessor>()
        val settings = mockk<SettingsRepository>()
        val promotion = mockk<PromotionalContentFilter>()
        val items = (1..5).map { n -> mockk<RssItem>(relaxed = true) {
            every { link } returns article(n).originalUrl
            every { title } returns "Article $n"
        } }
        coEvery { rss.fetchFeedForGeneration(feed.url) } returns items
        every { settings.getMinWordCount() } returns 0
        every { promotion.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(false)
        coEvery { processor.processForGeneration(any(), any(), any(), any(), any(), any()) } answers {
            val url = firstArg<String>()
            if (url.endsWith("/1")) ContentProcessor.GenerationResult.Failed
            else ContentProcessor.GenerationResult.Ready(article(url.substringAfterLast('/').toInt()))
        }
        val repository = ArticleRepository(rss, processor, mockk<OpenAIService>(),
            mockk<FeedRepository>(), settings, promotion, ledger)
        val one = repository.ingestForGeneration(feed, ledger.startRun(false))
        assertEquals(listOf(key(2)), one.delivered.map { it.identity })
        assertEquals(3, one.capDeferredCount)
        val two = repository.ingestForGeneration(feed, ledger.startRun(false))
        assertEquals(listOf(key(3), key(4)), two.delivered.map { it.identity })
        val three = repository.ingestForGeneration(feed, ledger.startRun(false))
        assertEquals(listOf(key(5)), three.delivered.map { it.identity })
        assertEquals(key(1).articleKey, db.articleDeliveryDao().forFeed(feed.url)
            .first { it.articleKey == key(1).articleKey }.articleKey)
    }

    @Test fun `transient summary failure retains full article and reports partial outcome`() = runBlocking {
        val briefing = feed.copy(mode = ProcessingMode.BRIEFING)
        val rss = mockk<RssService>()
        val processor = mockk<ContentProcessor>()
        val settings = mockk<SettingsRepository>()
        val promotion = mockk<PromotionalContentFilter>()
        val ai = mockk<OpenAIService>()
        val item = mockk<RssItem>(relaxed = true) {
            every { link } returns article(1).originalUrl
            every { title } returns "Article 1"
        }
        coEvery { rss.fetchFeedForGeneration(briefing.url) } returns listOf(item)
        every { settings.getMinWordCount() } returns 0
        every { promotion.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(false)
        coEvery { processor.processForGeneration(any(), any(), any(), any(), any(), any()) } returns
            ContentProcessor.GenerationResult.Ready(article(1))
        coEvery { ai.summarizeArticle(any()) } returns OpenAIService.ArticleSummaryResult.Failed
        val repository = ArticleRepository(rss, processor, ai, mockk<FeedRepository>(),
            settings, promotion, ledger)
        val result = repository.ingestForGeneration(briefing, ledger.startRun(false))
        assertEquals(article(1).content, result.delivered.single().article.content)
        assertFalse(result.delivered.single().article.isSummary)
        assertEquals(1, result.fallbackCount)
        assertEquals("full_article_fallback", result.failedItems.single().code)
        assertEquals("partial", GenerationDiagnostics(listOf(result)).outcome)
    }

    @Test fun `capped regeneration rotates five delivered items without rewriting first claims`() = runBlocking {
        (1..5).forEach { n ->
            commit(ledger.startRun(false), n, files.newFile("original-$n.epub"))
        }
        val claims = (1..5).associateWith { n ->
            db.articleDeliveryDao().get(feed.url, key(n).articleKey)!!
        }
        val rss = mockk<RssService>()
        val processor = mockk<ContentProcessor>()
        val settings = mockk<SettingsRepository>()
        val promotion = mockk<PromotionalContentFilter>()
        val items = (1..5).map { n -> mockk<RssItem>(relaxed = true) {
            every { link } returns article(n).originalUrl
            every { title } returns "Article $n"
        } }
        coEvery { rss.fetchFeedForGeneration(feed.url) } returns items
        every { settings.getMinWordCount() } returns 0
        every { promotion.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(false)
        coEvery { processor.processForGeneration(any(), any(), any(), any(), any(), any()) } answers {
            ContentProcessor.GenerationResult.Ready(article(firstArg<String>().substringAfterLast('/').toInt()))
        }
        val repository = ArticleRepository(rss, processor, mockk<OpenAIService>(),
            mockk<FeedRepository>(), settings, promotion, ledger)
        val selections = (1..3).map {
            repository.ingestForGeneration(feed, ledger.startRun(true), true)
                .delivered.map { it.identity }
        }
        assertEquals(listOf(key(1), key(2)), selections[0])
        assertEquals(listOf(key(3), key(4)), selections[1])
        assertEquals(listOf(key(5), key(1)), selections[2])
        (1..5).forEach { n ->
            val current = db.articleDeliveryDao().get(feed.url, key(n).articleKey)!!
            assertEquals("delivered", current.state)
            assertEquals(claims[n]!!.firstDigestId, current.firstDigestId)
            assertEquals(claims[n]!!.committedAt, current.committedAt)
        }
    }

    @Test fun `latest finished diagnostics stream survives database reopen`() = runBlocking {
        val name = "delivery-" + files.root.name + ".db"
        val context = RuntimeEnvironment.getApplication()
        context.deleteDatabase(name)
        fun open() = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
            .allowMainThreadQueries().build()
        var persisted = open()
        val store = ArticleDeliveryStore(persisted, persisted.articleDeliveryDao(),
            persisted.generationRunDao())
        val run = store.startRun(false)
        store.finishWithoutDigest(run, "deferred",
            """{"delivered_count":0,"filtered_count":2,"cap_deferred_count":3,"failed_count":0,
                "reason_counts":{"content_too_short":2}}""")
        persisted.close()
        persisted = open()
        val latest = persisted.generationRunDao().observeLatestFinished().first()
        assertEquals(run, latest?.runId)
        assertEquals("deferred", latest?.outcome)
        assertTrue(latest!!.diagnosticsJson.contains("content_too_short"))
        persisted.close()
    }

    @Test fun `generation deduplicates links and ignores missing or late publication dates`() = runBlocking {
        val source = feed.copy(maxArticles = 0, lastFetched = Long.MAX_VALUE)
        val rss = mockk<RssService>()
        val processor = mockk<ContentProcessor>()
        val settings = mockk<SettingsRepository>()
        val promotion = mockk<PromotionalContentFilter>()
        val items = listOf(1, 1, 2, 3).mapIndexed { index, n ->
            mockk<RssItem>(relaxed = true) {
                every { link } returns article(n).originalUrl
                every { title } returns "Article $n"
                every { pubDate } returns if (index == 2) null else "Mon, 01 Jan 2024 00:00:00 GMT"
            }
        }
        coEvery { rss.fetchFeedForGeneration(source.url) } returns items
        every { settings.getMinWordCount() } returns 0
        every { promotion.isPromotional(any(), any(), any()) } returns
            PromotionalContentFilter.FilterResult(false)
        coEvery { processor.processForGeneration(any(), any(), any(), any(), any(), any()) } answers {
            ContentProcessor.GenerationResult.Ready(article(firstArg<String>().substringAfterLast('/').toInt()))
        }
        val repository = ArticleRepository(rss, processor, mockk<OpenAIService>(),
            mockk<FeedRepository>(), settings, promotion, ledger)
        val result = repository.ingestForGeneration(source, ledger.startRun(false))
        assertEquals(4, result.candidateCount)
        assertEquals(3, result.selectedCount)
        assertEquals(listOf(key(1), key(2), key(3)), result.delivered.map { it.identity })
        coVerify(exactly = 0) { rss.fetchNewArticles(any(), any()) }
    }
}
