package com.example.epilogue.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface GenerationRunDao {
    @Insert
    suspend fun insert(row: GenerationRunEntity): Long

    @Query("SELECT * FROM generation_runs WHERE runId = :runId")
    suspend fun get(runId: Long): GenerationRunEntity?

    @Query("SELECT * FROM generation_runs WHERE outcome != 'running' ORDER BY runId DESC LIMIT 1")
    fun observeLatestFinished(): Flow<GenerationRunEntity?>

    @Query("UPDATE generation_runs SET finishedAt = :finishedAt, outcome = :outcome, " +
        "digestId = :digestId, diagnosticsJson = :diagnosticsJson WHERE runId = :runId")
    suspend fun finish(runId: Long, finishedAt: Long, outcome: String,
        digestId: Long?, diagnosticsJson: String)
}
