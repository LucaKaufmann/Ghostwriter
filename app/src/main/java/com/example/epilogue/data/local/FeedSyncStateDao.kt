package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface FeedSyncStateDao {
    @Query("SELECT * FROM feed_sync_state WHERE active = 1 LIMIT 1")
    suspend fun active(): FeedSyncStateEntity?

    @Query("SELECT * FROM feed_sync_state WHERE active = 1 LIMIT 1")
    fun activeFlow(): Flow<FeedSyncStateEntity?>

    @Query("SELECT * FROM feed_sync_state WHERE serverKey = :serverKey")
    suspend fun byKey(serverKey: String): FeedSyncStateEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(row: FeedSyncStateEntity)
}
