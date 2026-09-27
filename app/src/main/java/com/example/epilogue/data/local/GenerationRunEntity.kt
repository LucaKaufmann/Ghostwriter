package com.example.epilogue.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

/** The auto-incrementing run ID is also the monotonic local attempt sequence. */
@Entity(tableName = "generation_runs")
data class GenerationRunEntity(
    @PrimaryKey(autoGenerate = true) val runId: Long = 0,
    val startedAt: Long,
    val finishedAt: Long? = null,
    val outcome: String = "running",
    val digestId: Long? = null,
    val diagnosticsJson: String = "{}",
    val regeneration: Boolean = false,
    val triggerType: String? = null,
    val period: String? = null,
    val occurrenceDate: String? = null,
    val workId: String? = null
)
