package com.example.epilogue.shared.sync

import com.example.epilogue.shared.ghostwriter.DigestArticlesResponse
import com.example.epilogue.shared.ghostwriter.DigestResponse
import com.example.epilogue.shared.ghostwriter.SyncDigest

sealed class DigestSyncPlan {
    data class Combined(
        val digests: List<SyncDigest>,
        val shouldDownloadEpubs: Boolean
    ) : DigestSyncPlan()

    data class Legacy(
        val digests: List<DigestResponse>,
        val shouldDownloadEpubs: Boolean
    ) : DigestSyncPlan()

    data object NotConfigured : DigestSyncPlan()
    data class Error(val message: String) : DigestSyncPlan()
}

class DigestSyncUseCase(
    private val settings: SettingsPort,
    private val digestStore: DigestStorePort,
    private val ghostwriter: GhostwriterSyncPort
) {
    suspend fun planSync(): DigestSyncPlan {
        if (!settings.isGhostwriterConfigured()) {
            return DigestSyncPlan.NotConfigured
        }

        val shouldDownloadEpubs = settings.shouldDownloadGhostwriterEpubsOnSync()
        val existingRemoteIds = digestStore.getAllRemoteIds()
        val feedSince = settings.getLastFeedSyncTimeMillis()?.let { epochMillisToIso8601(it) }
        val digestIds = existingRemoteIds.takeIf { it.isNotEmpty() }?.joinToString(",")

        val combined = ghostwriter.performSync(feedSince = feedSince, digestIds = digestIds)
        when (combined) {
            is SyncPortResult.Success -> {
                return DigestSyncPlan.Combined(
                    digests = combined.data.digests.newDigests,
                    shouldDownloadEpubs = shouldDownloadEpubs
                )
            }
            is SyncPortResult.NotConfigured -> return DigestSyncPlan.NotConfigured
            is SyncPortResult.Error -> Unit
        }

        val legacy = ghostwriter.listDigests()
        return when (legacy) {
            is SyncPortResult.Success -> {
                val existing = existingRemoteIds.toSet()
                val newDigests = legacy.data.digests.filter { digest ->
                    digest.status == "completed" && digest.id !in existing
                }
                DigestSyncPlan.Legacy(
                    digests = newDigests,
                    shouldDownloadEpubs = shouldDownloadEpubs
                )
            }
            is SyncPortResult.NotConfigured -> DigestSyncPlan.NotConfigured
            is SyncPortResult.Error -> DigestSyncPlan.Error(legacy.message)
        }
    }

    suspend fun getDigestArticles(digestId: String): SyncPortResult<DigestArticlesResponse> {
        return ghostwriter.getDigestArticles(digestId)
    }
}
