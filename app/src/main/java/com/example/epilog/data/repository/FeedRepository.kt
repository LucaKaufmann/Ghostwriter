package com.example.epilog.data.repository

import com.example.epilog.data.local.FeedDao
import com.example.epilog.data.local.FeedEntity
import com.example.epilog.domain.model.Feed
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
}
