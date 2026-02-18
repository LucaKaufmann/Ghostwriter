package com.example.epilogue.shared

import kotlinx.serialization.Serializable

@Serializable
data class SharedModuleInfo(
    val name: String = "EpilogueShared",
    val version: String = "0.1.0"
)
