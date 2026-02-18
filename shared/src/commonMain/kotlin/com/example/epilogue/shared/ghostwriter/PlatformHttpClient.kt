package com.example.epilogue.shared.ghostwriter

import io.ktor.client.HttpClient

internal expect fun createPlatformHttpClient(): HttpClient
