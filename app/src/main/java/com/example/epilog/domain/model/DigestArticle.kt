package com.example.epilog.domain.model

/**
 * Domain model for an article stored within a digest.
 */
data class DigestArticle(
    val id: Long,
    val title: String,
    val author: String,
    val content: String,
    val originalUrl: String,
    val isSummary: Boolean,
    val feedName: String
)
