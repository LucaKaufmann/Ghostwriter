package com.example.epilogue.data.local

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/** One durable proposal. A sent row's payload/base/revision must never be edited. */
@Entity(tableName = "feed_mutations", indices = [Index(value = ["serverKey", "url", "sequence"], unique = true)])
data class FeedMutationEntity(
    @PrimaryKey val opId: String,
    val serverKey: String,
    val url: String,
    val kind: String,
    val baseVersion: Long?,
    val fieldsJson: String,
    val localRevision: Long,
    val state: String,
    val serverSnapshotJson: String? = null,
    val createdAt: Long,
    val sequence: Long,
    val queueOrder: Long,
    @ColumnInfo(defaultValue = "0") val sent: Boolean = false,
    val rejectionCode: String? = null,
    val rejectionMessage: String? = null
)
