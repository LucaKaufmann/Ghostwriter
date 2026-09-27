package com.example.epilogue.sync

import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchResultV2
import com.example.epilogue.shared.ghostwriter.FeedMutationBatchV2
import com.example.epilogue.shared.ghostwriter.GhostwriterClientHandle
import com.example.epilogue.shared.sync.FeedV2Destination
import com.example.epilogue.shared.sync.FeedV2RemotePort
import com.example.epilogue.shared.sync.FeedV2RemoteResult
import kotlinx.coroutines.CancellationException
import javax.inject.Inject
import javax.inject.Singleton

/** Both settings client modes use the same guarded v2 transport for feed writes. */
@Singleton
class AndroidFeedV2RemotePort @Inject constructor(
    private val settings: SettingsRepository
) : FeedV2RemotePort {
    private suspend fun <T> withClient(destination: FeedV2Destination,
        call: suspend (GhostwriterClientHandle) -> FeedV2RemoteResult<T>): FeedV2RemoteResult<T> {
        if (!settings.isGhostwriterConfigured() ||
            settings.getGhostwriterUrl()?.trim()?.trimEnd('/')?.removeSuffix("/api") != destination.normalizedBaseUrl) {
            return FeedV2RemoteResult.TransportFailure("Destination changed")
        }
        val handle = GhostwriterClientHandle.create(destination.normalizedBaseUrl, settings.getGhostwriterApiKey())
        try {
            return call(handle)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            return FeedV2RemoteResult.TransportFailure(error.message ?: "Transport failure")
        } finally {
            handle.close()
        }
    }

    override suspend fun getFeedChangesV2(destination: FeedV2Destination, sinceVersion: Long?,
        serverInstanceId: String?): FeedV2RemoteResult<FeedChangesV2Response> =
        withClient(destination) { it.client.getFeedChangesV2(destination, sinceVersion, serverInstanceId) }

    override suspend fun postFeedMutationsV2(destination: FeedV2Destination,
        batch: FeedMutationBatchV2): FeedV2RemoteResult<FeedMutationBatchResultV2> =
        withClient(destination) { it.client.postFeedMutationsV2(destination, batch) }
}
