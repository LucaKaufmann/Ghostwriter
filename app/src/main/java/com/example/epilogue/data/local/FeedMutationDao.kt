package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface FeedMutationDao {
    @Query("SELECT * FROM feed_mutations WHERE serverKey = :serverKey ORDER BY url, sequence")
    suspend fun forScope(serverKey: String): List<FeedMutationEntity>

    @Query("SELECT * FROM feed_mutations WHERE url = :url ORDER BY sequence")
    suspend fun forUrl(url: String): List<FeedMutationEntity>

    @Query("SELECT candidate.* FROM feed_mutations AS candidate " +
        "WHERE candidate.state IN ('needs_resolution','rejected') " +
        "AND candidate.serverKey = (SELECT serverKey FROM feed_sync_state WHERE active = 1 LIMIT 1) " +
        "AND NOT EXISTS (SELECT 1 FROM feed_mutations AS earlier " +
        "WHERE earlier.serverKey = candidate.serverKey AND earlier.url = candidate.url " +
        "AND (earlier.queueOrder < candidate.queueOrder OR " +
        "(earlier.queueOrder = candidate.queueOrder AND earlier.sequence < candidate.sequence))) " +
        "ORDER BY candidate.createdAt, candidate.sequence")
    fun unresolvedFlow(): Flow<List<FeedMutationEntity>>

    @Query("SELECT * FROM feed_mutations WHERE opId = :opId")
    suspend fun byId(opId: String): FeedMutationEntity?

    @Insert
    suspend fun insert(row: FeedMutationEntity)

    @Update
    suspend fun update(row: FeedMutationEntity)

    @Query("DELETE FROM feed_mutations WHERE opId = :opId")
    suspend fun deleteById(opId: String)

    @Query("UPDATE feed_mutations SET serverKey = :newKey WHERE serverKey = :oldKey")
    suspend fun moveScope(oldKey: String, newKey: String)
}
