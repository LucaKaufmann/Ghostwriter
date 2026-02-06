package com.example.epilogue.domain.model

data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String,  // HTML or Markdown
    val originalUrl: String,
    val isSummary: Boolean,
    val feedUrl: String = "",
    val feedName: String = ""
)
