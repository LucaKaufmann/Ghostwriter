package com.example.epilogue.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

/** One row per destination scope, including the initial local-only scope. */
@Entity(tableName = "feed_sync_state")
data class FeedSyncStateEntity(
    @PrimaryKey val serverKey: String,
    val bindingUrl: String? = null,
    val configurationId: String? = null,
    val serverInstanceId: String? = null,
    val cursorVersion: Long? = null,
    val firstBindingComplete: Boolean = false,
    val nextSequence: Long = 1,
    val generation: Long = 0,
    val active: Boolean = false,
    val suspended: Boolean = false,
    val lastOutcome: String? = null,
    val lastDiagnostic: String? = null
)
