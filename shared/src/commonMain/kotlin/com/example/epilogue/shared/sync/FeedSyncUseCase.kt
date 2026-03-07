package com.example.epilogue.shared.sync

import com.example.epilogue.shared.domain.Feed
import com.example.epilogue.shared.domain.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedResponse
import com.example.epilogue.shared.ghostwriter.FeedSyncRequest
import kotlinx.datetime.Clock

sealed class FeedSyncOutcome {
    data class Success(
        val pushed: Boolean,
        val updatedFeeds: Int,
        val deletedFeeds: Int
    ) : FeedSyncOutcome()

    data class Error(val message: String) : FeedSyncOutcome()
    data object NotConfigured : FeedSyncOutcome()
}

class FeedSyncUseCase(
    private val settings: SettingsPort,
    private val feedStore: FeedStorePort,
    private val ghostwriter: GhostwriterSyncPort,
    private val nowProviderMillis: () -> Long = { Clock.System.now().toEpochMilliseconds() }
) {
    suspend fun sync(): FeedSyncOutcome {
        if (!settings.isGhostwriterConfigured()) {
            return FeedSyncOutcome.NotConfigured
        }

        val pushed = pushLocalFeeds()

        val since = settings.getLastFeedSyncTimeMillis()?.let { epochMillisToIso8601(it) }
        val changesResult = ghostwriter.getFeedChanges(since)

        return when (changesResult) {
            is SyncPortResult.Success -> {
                val changes = changesResult.data

                val feeds = changes.feeds.map { it.toDomainFeed() }
                if (feeds.isNotEmpty()) {
                    feedStore.upsertAll(feeds)
                }

                val tombstoneUrls = changes.tombstones.map { it.url }
                if (tombstoneUrls.isNotEmpty()) {
                    feedStore.deleteByUrls(tombstoneUrls)
                }

                if (pushed) {
                    feedStore.clearAllLocallyModified()
                }

                val parsedServerTime = parseIso8601ToEpochMillis(changes.serverTimestamp)
                settings.setLastFeedSyncTimeMillis(parsedServerTime ?: nowProviderMillis())

                FeedSyncOutcome.Success(
                    pushed = pushed,
                    updatedFeeds = feeds.size,
                    deletedFeeds = tombstoneUrls.size
                )
            }
            is SyncPortResult.Error -> FeedSyncOutcome.Error(changesResult.message)
            is SyncPortResult.NotConfigured -> FeedSyncOutcome.NotConfigured
        }
    }

    private suspend fun pushLocalFeeds(): Boolean {
        val localFeeds = feedStore.getAllFeeds()
        if (localFeeds.isEmpty()) return true

        val requests = localFeeds
            .filterNot { it.url.startsWith("synthetic://") }
            .map { feed ->
                FeedSyncRequest(
                    url = feed.url,
                    title = feed.name,
                    isActive = feed.isEnabled,
                    mode = when (feed.mode) {
                        ProcessingMode.BRIEFING -> "summarize"
                        ProcessingMode.FIDELITY -> "raw"
                    },
                    maxArticles = if (feed.maxArticles > 0) feed.maxArticles else 10
                )
            }

        return when (ghostwriter.syncFeeds(requests)) {
            is SyncPortResult.Success -> true
            is SyncPortResult.Error,
            is SyncPortResult.NotConfigured -> false
        }
    }

    private fun FeedResponse.toDomainFeed(): Feed {
        val mode = if (mode == "summarize") ProcessingMode.BRIEFING else ProcessingMode.FIDELITY

        return Feed(
            url = url,
            name = title,
            mode = mode,
            maxArticles = maxArticles,
            isEnabled = isActive,
            serverUpdatedAtEpochMillis = parseIso8601ToEpochMillis(updatedAt),
            locallyModified = false
        )
    }
}
