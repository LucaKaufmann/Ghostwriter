package com.example.epilog.service

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.example.epilog.data.repository.ArticleRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.Date

/**
 * WorkManager worker that generates the daily EPUB digest.
 * Fetches articles from all configured feeds, processes them according to their mode,
 * and generates an EPUB file.
 */
@HiltWorker
class DailyDigestWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted workerParams: WorkerParameters,
    private val articleRepository: ArticleRepository,
    private val epubGenerator: EpubGenerator
) : CoroutineWorker(context, workerParams) {

    companion object {
        const val TAG = "DailyDigestWorker"
        const val WORK_NAME = "daily_digest_work"

        // Input data keys
        const val KEY_FETCH_ALL = "fetch_all"  // If true, fetch all articles (not just new)
    }

    override suspend fun doWork(): Result {
        Log.i(TAG, "Starting daily digest generation")

        return try {
            val fetchOnlyNew = !inputData.getBoolean(KEY_FETCH_ALL, false)

            // Fetch and process articles from all feeds
            val articles = articleRepository.fetchFromAllFeeds(onlyNew = fetchOnlyNew)

            if (articles.isEmpty()) {
                Log.i(TAG, "No articles to process")
                return Result.success()
            }

            Log.i(TAG, "Fetched ${articles.size} articles")

            // Generate EPUB
            val epubFile = epubGenerator.generate(articles, Date())

            if (epubFile != null) {
                Log.i(TAG, "Generated EPUB: ${epubFile.absolutePath}")
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
