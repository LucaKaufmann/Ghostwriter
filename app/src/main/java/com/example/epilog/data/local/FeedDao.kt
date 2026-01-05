package com.example.epilog.data.local

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface FeedDao {
    @Query("SELECT * FROM feeds ORDER BY name ASC")
    fun getAllFeeds(): Flow<List<FeedEntity>>

    @Query("SELECT * FROM feeds ORDER BY name ASC")
    suspend fun getAllFeedsList(): List<FeedEntity>

    @Query("SELECT * FROM feeds WHERE url = :url")
    suspend fun getFeedByUrl(url: String): FeedEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFeed(feed: FeedEntity)

    @Update
    suspend fun updateFeed(feed: FeedEntity)

    @Delete
    suspend fun deleteFeed(feed: FeedEntity)

    @Query("UPDATE feeds SET lastFetched = :timestamp WHERE url = :url")
    suspend fun updateLastFetched(url: String, timestamp: Long)
}
