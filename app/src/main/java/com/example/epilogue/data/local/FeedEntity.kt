package com.example.epilogue.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode

@Entity(tableName = "feeds")
data class FeedEntity(
    @PrimaryKey val url: String,
    val name: String,
    val mode: ProcessingMode,
    val lastFetched: Long = 0L,
    val maxArticles: Int = 0,  // 0 = unlimited
    // Sync fields for bi-directional sync with Ghostwriter
    val serverUpdatedAt: Long? = null,    // Server's updated_at timestamp (millis)
    val locallyModified: Boolean = false   // Needs push to server
) {
    fun toDomain(): Feed = Feed(
        url = url,
        name = name,
        mode = mode,
        lastFetched = lastFetched,
        maxArticles = maxArticles,
        serverUpdatedAt = serverUpdatedAt,
        locallyModified = locallyModified
    )

    companion object {
        fun fromDomain(feed: Feed): FeedEntity = FeedEntity(
            url = feed.url,
            name = feed.name,
            mode = feed.mode,
            lastFetched = feed.lastFetched,
            maxArticles = feed.maxArticles,
            serverUpdatedAt = feed.serverUpdatedAt,
            locallyModified = feed.locallyModified
        )
    }
}
