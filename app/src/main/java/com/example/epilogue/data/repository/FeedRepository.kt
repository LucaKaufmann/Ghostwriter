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
    private val feedDao: FeedDao,
    private val feedV2Store: AndroidFeedV2Store
) {
    fun getAllFeeds(): Flow<List<Feed>> =
        feedDao.getAllFeeds().map { entities ->
            entities.map { it.toDomain() }
        }

    suspend fun getAllFeedsList(): List<Feed> =
        feedDao.getAllFeedsList().map { it.toDomain() }

    suspend fun getEnabledFeedsList(): List<Feed> =
        feedDao.getEnabledFeedsList().map { it.toDomain() }

    suspend fun getFeedByUrl(url: String): Feed? =
        feedDao.getFeedByUrl(url)?.toDomain()

    suspend fun insertFeed(feed: Feed) {
        feedV2Store.saveLocal(feed)
    }

    suspend fun updateFeed(feed: Feed) {
        feedV2Store.saveLocal(feed)
    }

    suspend fun deleteFeed(feed: Feed) {
        feedV2Store.deleteLocal(feed.url)
    }

    suspend fun updateLastFetched(url: String, timestamp: Long) {
        feedDao.updateLastFetched(url, timestamp)
    }

    suspend fun resetAllLastFetched() {
        feedDao.resetAllLastFetched()
    }

    /**
     * Insert a feed and mark it as locally modified for sync.
     */
    suspend fun insertFeedWithSync(feed: Feed) {
        feedV2Store.saveLocal(feed)
    }

    /**
     * Update a feed and mark it as locally modified for sync.
     */
    suspend fun updateFeedWithSync(feed: Feed) {
        feedV2Store.saveLocal(feed)
    }
}
