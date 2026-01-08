package com.example.epilogue.service

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.example.epilogue.data.repository.ArticleRepository
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.domain.model.TriggerType
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.Date

/**
 * WorkManager worker that generates the daily EPUB digest.
 * Fetches articles from all configured feeds, processes them according to their mode,
 * and generates an EPUB file. Also saves the digest to history.
 */
@HiltWorker
class DailyDigestWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val articleRepository: ArticleRepository,
    private val feedRepository: FeedRepository,
    private val digestRepository: DigestRepository,
    private val epubGenerator: EpubGenerator,
    private val epubExporter: EpubExporter
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DailyDigestWorker"
        const val WORK_NAME = "daily_digest_work"

        // Input data keys
        const val KEY_FETCH_ALL = "fetch_all"  // If true, fetch all articles (not just new)
        const val KEY_IS_MANUAL = "is_manual"  // If true, triggered manually (not scheduled)
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting daily digest generation")

        return try {
            val fetchOnlyNew = !inputData.getBoolean(KEY_FETCH_ALL, false)
            val isManual = inputData.getBoolean(KEY_IS_MANUAL, false)

            // Get all feeds for later reference
            val feeds = feedRepository.getAllFeedsList()

            // Fetch and process articles from all feeds
            val articles = articleRepository.fetchFromAllFeeds(onlyNew = fetchOnlyNew)

            if (articles.isEmpty()) {
                Log.i(TAG, "No articles to process")
                return Result.success()
            }

            Log.i(TAG, "Fetched ${articles.size} articles")

            // Generate EPUB
            val result = epubGenerator.generate(articles, Date())

            if (result != null) {
                Log.i(TAG, "Generated EPUB: ${result.file.absolutePath}")

                // Export to custom directory if configured
                when (val exportResult = epubExporter.exportToCustomDirectory(result.file)) {
                    is ExportResult.Success ->
                        Log.i(TAG, "Exported to custom directory")
                    is ExportResult.PermissionRevoked ->
                        Log.w(TAG, "Custom export permission revoked")
                    is ExportResult.Error ->
                        Log.e(TAG, "Custom export failed: ${exportResult.message}")
                    ExportResult.NotConfigured -> { /* No-op */ }
                }

                // Save to digest history
                val triggerType = if (isManual) TriggerType.MANUAL else TriggerType.SCHEDULED
                digestRepository.saveDigest(
                    articles = result.articles,
                    feeds = feeds,
                    epubFilePath = result.file.absolutePath,
                    triggerType = triggerType
                )
                Log.i(TAG, "Saved digest to history")

                Result.success()
            } else {
                Log.e(TAG, "Failed to generate EPUB")
                Result.failure()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error generating digest", e)
            Result.failure()
        }
    }
}
