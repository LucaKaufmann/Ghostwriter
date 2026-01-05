package com.example.epilog.domain.model

data class ProcessedArticle(
    val title: String,
    val author: String,
    val content: String,  // HTML or Markdown
    val originalUrl: String,
    val isSummary: Boolean
)
