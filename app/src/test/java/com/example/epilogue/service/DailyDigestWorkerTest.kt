package com.example.epilogue.service

import androidx.room.Room
import androidx.work.Data
import androidx.work.WorkerParameters
import androidx.work.ForegroundUpdater
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.repository.ArticleDeliveryStore
import com.example.epilogue.data.repository.ArticleRepository
import com.example.epilogue.data.repository.DeliveredArticle
import com.example.epilogue.data.repository.DeliveryIdentity
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedIngestionResult
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessedArticle
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.delivery.ArticleDeliveryIdentity
import com.example.epilogue.shared.delivery.ArticleIdentityResult
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
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
import java.io.IOException
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class DailyDigestWorkerTest {
    @get:Rule val files = TemporaryFolder()
    private lateinit var db: EpilogueDatabase
    private lateinit var ledger: ArticleDeliveryStore
    private lateinit var history: DigestRepository
    private val article = ProcessedArticle("Fixture", "Author", "<p>Body</p>",
        "https://example.test/article", false, feedUrl = "https://example.test/feed",
        feedName = "Fixture")
    private val feed = Feed(article.feedUrl, "Fixture", ProcessingMode.FIDELITY)
    private val key = (ArticleDeliveryIdentity().fromArticleLink(article.originalUrl)
        as ArticleIdentityResult.Valid).articleKey

    @Before fun setUp() {
        db = Room.inMemoryDatabaseBuilder(RuntimeEnvironment.getApplication(), EpilogueDatabase::class.java)
            .allowMainThreadQueries().build()
        ledger = ArticleDeliveryStore(db, db.articleDeliveryDao(), db.generationRunDao())
        history = DigestRepository(db.digestDao(), db, db.articleDeliveryDao(),
            db.generationRunDao())
    }

    @After fun tearDown() { db.close() }

    @Test fun `artifact failure remains retryable and next run commits despite export failure`() = runBlocking {
        val params = mockk<WorkerParameters>(relaxed = true)
        every { params.id } returns UUID.randomUUID()
        every { params.inputData } returns Data.Builder()
            .putBoolean(DailyDigestWorker.KEY_IS_MANUAL, true).build()
        every { params.runAttemptCount } returns 3
        val foreground = mockk<ForegroundUpdater>()
        every { foreground.setForegroundAsync(any(), any(), any()) } throws
            IllegalStateException("foreground unavailable in fixture")
        every { params.foregroundUpdater } returns foreground
        val settings = mockk<SettingsRepository>()
        every { settings.isGhostwriterConfigured() } returns false
        val feeds = mockk<FeedRepository>()
        coEvery { feeds.getEnabledFeedsList() } returns listOf(feed)
        val source = mockk<ArticleRepository>()
        coEvery { source.ingestForGeneration(feed, any(), false) } coAnswers {
            val runId = secondArg<Long>()
            ledger.markAttempts(runId, listOf(DeliveryIdentity(feed.url, key)), "fixture", false)
            FeedIngestionResult(feed, 1, 1,
                listOf(DeliveredArticle(DeliveryIdentity(feed.url, key), article, "fixture")),
                emptyList(), emptyList(), 0)
        }
        val generator = mockk<EpubGenerator>()
        val file = files.root.resolve("retry.epub")
        coEvery { generator.generate(any(), any(), any()) } returnsMany
            listOf(null, EpubGenerationResult(file, listOf(article)))
        val exporter = mockk<EpubExporter>()
        coEvery { exporter.exportToCustomDirectory(file) } throws IOException("fixture export failure")
        fun worker() = DailyDigestWorker(RuntimeEnvironment.getApplication(), params, source,
            feeds, history, settings, generator, exporter, ledger, GenerationGate())

        worker().doWork()
        assertEquals("failed", db.generationRunDao().observeLatestFinished().first()?.outcome)
        assertEquals("retryable", db.articleDeliveryDao().get(feed.url, key)?.state)
        assertEquals(0, db.digestDao().getDigestCount())

        file.writeText("synthetic")
        worker().doWork()
        assertEquals("complete", db.generationRunDao().observeLatestFinished().first()?.outcome)
        assertEquals("delivered", db.articleDeliveryDao().get(feed.url, key)?.state)
        assertEquals(1, db.digestDao().getDigestCount())
        assertTrue(file.exists())
        coVerify(exactly = 1) { exporter.exportToCustomDirectory(file) }
    }
}
