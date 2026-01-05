package com.example.epilog.domain.model

data class Feed(
    val url: String,
    val name: String,
    val mode: ProcessingMode,
    val lastFetched: Long = 0L
)
