package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface FeedDao {
    @Query("SELECT * FROM feeds WHERE hiddenDelete = 0 ORDER BY name ASC")
    fun getAllFeeds(): Flow<List<FeedEntity>>

    @Query("SELECT * FROM feeds WHERE hiddenDelete = 0 ORDER BY name ASC")
    suspend fun getAllFeedsList(): List<FeedEntity>

    @Query("SELECT * FROM feeds WHERE isEnabled = 1 AND hiddenDelete = 0 " +
        "AND url NOT IN (SELECT url FROM feed_mutations WHERE state = 'legacy_unresolved' " +
        "AND serverKey = (SELECT serverKey FROM feed_sync_state WHERE active = 1 LIMIT 1)) ORDER BY name ASC")
    suspend fun getEnabledFeedsList(): List<FeedEntity>

    @Query("SELECT * FROM feeds WHERE url = :url")
    suspend fun getFeedByUrl(url: String): FeedEntity?

    @Query("SELECT * FROM feeds WHERE url NOT LIKE 'synthetic://%' ORDER BY url")
    suspend fun getAllRealFeedsIncludingHidden(): List<FeedEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFeed(feed: FeedEntity)

    @Update
    suspend fun updateFeed(feed: FeedEntity)

    @Delete
    suspend fun deleteFeed(feed: FeedEntity)

    @Query("UPDATE feeds SET lastFetched = :timestamp WHERE url = :url")
    suspend fun updateLastFetched(url: String, timestamp: Long)

    @Query("UPDATE feeds SET lastFetched = 0")
    suspend fun resetAllLastFetched()

}
