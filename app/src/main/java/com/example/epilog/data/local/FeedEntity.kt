package com.example.epilog.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.example.epilog.domain.model.Feed
import com.example.epilog.domain.model.ProcessingMode

@Entity(tableName = "feeds")
data class FeedEntity(
    @PrimaryKey val url: String,
    val name: String,
    val mode: ProcessingMode,
    val lastFetched: Long = 0L
) {
    fun toDomain(): Feed = Feed(
        url = url,
        name = name,
        mode = mode,
        lastFetched = lastFetched
    )

    companion object {
        fun fromDomain(feed: Feed): FeedEntity = FeedEntity(
            url = feed.url,
            name = feed.name,
            mode = feed.mode,
            lastFetched = feed.lastFetched
        )
    }
}
