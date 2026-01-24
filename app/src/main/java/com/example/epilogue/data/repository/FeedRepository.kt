package com.example.epilogue.data.repository

import com.example.epilogue.data.local.FeedDao
import com.example.epilogue.data.local.FeedEntity
import com.example.epilogue.domain.model.Feed
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FeedRepository @Inject constructor(
    private val feedDao: FeedDao
) {
    fun getAllFeeds(): Flow<List<Feed>> =
        feedDao.getAllFeeds().map { entities ->
            entities.map { it.toDomain() }
        }

    suspend fun getAllFeedsList(): List<Feed> =
        feedDao.getAllFeedsList().map { it.toDomain() }

    suspend fun getFeedByUrl(url: String): Feed? =
        feedDao.getFeedByUrl(url)?.toDomain()

    suspend fun insertFeed(feed: Feed) {
        feedDao.insertFeed(FeedEntity.fromDomain(feed))
    }

    suspend fun updateFeed(feed: Feed) {
        feedDao.updateFeed(FeedEntity.fromDomain(feed))
    }

    suspend fun deleteFeed(feed: Feed) {
        feedDao.deleteFeed(FeedEntity.fromDomain(feed))
    }

    suspend fun updateLastFetched(url: String, timestamp: Long) {
        feedDao.updateLastFetched(url, timestamp)
    }

    suspend fun resetAllLastFetched() {
        feedDao.resetAllLastFetched()
    }

    // ===== Sync Methods for Bi-Directional Sync =====

    /**
     * Get all feeds that have local modifications pending sync to server.
     */
    suspend fun getLocallyModifiedFeeds(): List<Feed> =
        feedDao.getLocallyModifiedFeeds().map { it.toDomain() }

    /**
     * Clear the locallyModified flag on all feeds after successful sync.
     */
    suspend fun clearAllLocallyModified() {
        feedDao.clearAllLocallyModified()
    }

    /**
     * Delete feeds by their URLs (used for applying tombstones from server).
     */
    suspend fun deleteByUrls(urls: List<String>) {
        if (urls.isNotEmpty()) {
            feedDao.deleteByUrls(urls)
        }
    }

    /**
     * Upsert multiple feeds at once (used for applying server changes).
     * This replaces feeds with matching URLs.
     */
    suspend fun upsertAll(feeds: List<Feed>) {
        if (feeds.isNotEmpty()) {
            feedDao.upsertAll(feeds.map { FeedEntity.fromDomain(it) })
        }
    }

    /**
     * Mark a feed as locally modified (needs sync to server).
     */
    suspend fun markAsLocallyModified(url: String) {
        feedDao.markAsLocallyModified(url)
    }

    /**
     * Insert a feed and mark it as locally modified for sync.
     */
    suspend fun insertFeedWithSync(feed: Feed) {
        val entityWithModifiedFlag = FeedEntity.fromDomain(feed.copy(locallyModified = true))
        feedDao.insertFeed(entityWithModifiedFlag)
    }

    /**
     * Update a feed and mark it as locally modified for sync.
     */
    suspend fun updateFeedWithSync(feed: Feed) {
        val entityWithModifiedFlag = FeedEntity.fromDomain(feed.copy(locallyModified = true))
        feedDao.updateFeed(entityWithModifiedFlag)
    }
}
