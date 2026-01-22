package com.example.epilogue.domain.model

/**
 * Domain model representing a generated digest.
 */
data class Digest(
    val id: Long,
    val generatedAt: Long,
    val epubFilePath: String,
    val articleCount: Int,
    val briefingCount: Int,
    val fidelityCount: Int,
    val triggerType: TriggerType,
    val feedNames: List<String>,
    val remoteId: String? = null  // Ghostwriter digest ID if synced from backend
)
