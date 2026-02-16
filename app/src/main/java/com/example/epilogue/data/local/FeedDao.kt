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
    @Query("SELECT * FROM feeds ORDER BY name ASC")
    fun getAllFeeds(): Flow<List<FeedEntity>>

    @Query("SELECT * FROM feeds ORDER BY name ASC")
    suspend fun getAllFeedsList(): List<FeedEntity>

    @Query("SELECT * FROM feeds WHERE isEnabled = 1 ORDER BY name ASC")
    suspend fun getEnabledFeedsList(): List<FeedEntity>

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

    @Query("UPDATE feeds SET lastFetched = 0")
    suspend fun resetAllLastFetched()

    // ===== Sync Methods =====

    /** Get all feeds that have local modifications pending sync to server. */
    @Query("SELECT * FROM feeds WHERE locallyModified = 1")
    suspend fun getLocallyModifiedFeeds(): List<FeedEntity>

    /** Clear the locallyModified flag on all feeds after successful sync. */
    @Query("UPDATE feeds SET locallyModified = 0")
    suspend fun clearAllLocallyModified()

    /** Delete feeds by their URLs (used for applying tombstones from server). */
    @Query("DELETE FROM feeds WHERE url IN (:urls)")
    suspend fun deleteByUrls(urls: List<String>)

    /** Upsert multiple feeds at once (used for applying server changes). */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertAll(feeds: List<FeedEntity>)

    /** Mark a feed as locally modified (needs sync to server). */
    @Query("UPDATE feeds SET locallyModified = 1 WHERE url = :url")
    suspend fun markAsLocallyModified(url: String)
}
