package com.example.epilogue.domain.model

data class Feed(
    val url: String,
    val name: String,
    val mode: ProcessingMode,
    val lastFetched: Long = 0L,
    val maxArticles: Int = 0,  // 0 = unlimited
    val isEnabled: Boolean = true,
    // Sync fields for bi-directional sync with Ghostwriter
    val serverUpdatedAt: Long? = null,    // Server's updated_at timestamp (millis)
    val locallyModified: Boolean = false   // Needs push to server
)
