package com.example.epilogue.data.local

import androidx.room.Entity

/** Installation-local identity. It deliberately has no history or feed foreign key. */
@Entity(tableName = "article_delivery", primaryKeys = ["feedUrl", "articleKey"])
data class ArticleDeliveryEntity(
    val feedUrl: String,
    val articleKey: String,
    val state: String,
    val reason: String? = null,
    val filterSignature: String? = null,
    val lastAttemptSequence: Long = 0,
    val firstDigestId: Long? = null,
    val committedAt: Long = 0
)
