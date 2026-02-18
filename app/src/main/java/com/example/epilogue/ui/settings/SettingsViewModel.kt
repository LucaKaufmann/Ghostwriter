package com.example.epilogue.ui.settings

import android.net.Uri
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import com.example.epilogue.data.remote.ghostwriter.ClientConfigResponse
import com.example.epilogue.data.remote.ghostwriter.DigestStatusResponse
import com.example.epilogue.data.remote.ghostwriter.HealthResponse
import com.example.epilogue.data.remote.ghostwriter.IntegrationStatus
import com.example.epilogue.data.remote.ghostwriter.MediaProcessingStatusResponse
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
import com.example.epilogue.service.ConfigSyncManager
import com.example.epilogue.service.DigestScheduler
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val settingsRepository: SettingsRepository,
    private val digestScheduler: DigestScheduler,
    private val digestRepository: DigestRepository,
    private val feedRepository: FeedRepository,
    private val ghostwriterRepository: GhostwriterRepository,
    private val configSyncManager: ConfigSyncManager
) : ViewModel() {

    companion object {
        private const val TAG = "SettingsViewModel"
    }

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    private var digestPollingJob: Job? = null

    init {
        loadSettings()
        if (settingsRepository.isGhostwriterConfigured()) {
            fetchIntegrationStatus()
            refreshMediaOverview()
            refreshLogFiles()
            refreshAuthTokens()
        }
    }

    private fun loadSettings() {
        val customExportUri = settingsRepository.getCustomExportUri()
        _uiState.update { state ->
            state.copy(
                apiKey = settingsRepository.getOpenAIApiKey() ?: "",
                selectedPeriods = settingsRepository.getSchedulePeriods(),
                minWordCount = settingsRepository.getMinWordCount(),
                einkMode = settingsRepository.getEinkMode(),
                customExportUri = customExportUri,
                customExportEnabled = settingsRepository.isCustomExportEnabled(),
                customExportDisplayPath = getDisplayPath(customExportUri),
                // Ghostwriter settings
                ghostwriterEnabled = settingsRepository.isGhostwriterEnabled(),
                ghostwriterUrl = settingsRepository.getGhostwriterUrl() ?: "",
                ghostwriterApiKey = settingsRepository.getGhostwriterApiKey() ?: "",
                ghostwriterDownloadEpubsOnSync = settingsRepository.shouldDownloadGhostwriterEpubsOnSync(),
                serverSchedule = settingsRepository.getGhostwriterSchedule()
            )
        }
    }

    fun updateApiKey(apiKey: String) {
        _uiState.update { it.copy(apiKey = apiKey) }
    }

    fun saveApiKey() {
        viewModelScope.launch {
            val apiKey = _uiState.value.apiKey.trim()
            settingsRepository.setOpenAIApiKey(apiKey.ifBlank { null })
            _uiState.update { it.copy(apiKeySaved = true) }
        }
    }

    fun togglePeriod(period: DigestPeriod, enabled: Boolean) {
        viewModelScope.launch {
            digestScheduler.updatePeriod(period, enabled)
            val updatedPeriods = _uiState.value.selectedPeriods.toMutableSet()
            if (enabled) {
                updatedPeriods.add(period)
            } else {
                updatedPeriods.remove(period)
            }
            _uiState.update { it.copy(selectedPeriods = updatedPeriods) }

            // Sync schedule to Ghostwriter if enabled
            if (settingsRepository.isGhostwriterConfigured()) {
                val result = ghostwriterRepository.updateSchedule(
                    period = period.name.lowercase(),
                    enabled = enabled
                )
                when (result) {
                    is GhostwriterResult.Success -> {
                        Log.i(TAG, "Synced schedule ${period.name} to Ghostwriter: enabled=$enabled")
                    }
                    is GhostwriterResult.Error -> {
                        Log.w(TAG, "Failed to sync schedule to Ghostwriter: ${result.message}")
                    }
                    is GhostwriterResult.NotConfigured -> { }
                }
            }
        }
    }

    fun updateMinWordCount(count: Int) {
        viewModelScope.launch {
            settingsRepository.setMinWordCount(count)
            _uiState.update { it.copy(minWordCount = count) }

            // Sync to Ghostwriter if enabled
            if (settingsRepository.isGhostwriterConfigured()) {
                configSyncManager.pushMinWordCount(count)
            }
        }
    }

    fun updateEinkMode(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepository.setEinkMode(enabled)
            _uiState.update { it.copy(einkMode = enabled) }
        }
    }

    fun runDigestNow() {
        if (_uiState.value.ghostwriterEnabled && _uiState.value.ghostwriterUrl.isNotBlank()) {
            // Use Ghostwriter backend
            runDigestViaGhostwriter()
        } else {
            // Use local generation
            runDigestLocally()
        }
    }

    private fun runDigestLocally() {
        _uiState.update { it.copy(isGenerating = true, digestTriggered = true) }
        digestScheduler.runNow(fetchAll = false)

        // Observe work completion
        digestScheduler.getImmediateWorkInfo().observeForever { workInfos ->
            val workInfo = workInfos?.firstOrNull() ?: return@observeForever
            when (workInfo.state) {
                WorkInfo.State.SUCCEEDED -> {
                    _uiState.update { it.copy(isGenerating = false, digestCompleted = true) }
                }
                WorkInfo.State.FAILED -> {
                    _uiState.update { it.copy(isGenerating = false, digestFailed = true) }
                }
                WorkInfo.State.CANCELLED -> {
                    _uiState.update { it.copy(isGenerating = false) }
                }
                else -> { /* Still running */ }
            }
        }
    }

    private fun runDigestViaGhostwriter() {
        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isGenerating = true,
                    digestTriggered = true,
                    ghostwriterProgress = null
                )
            }

            // First, sync feeds to Ghostwriter
            val feeds = feedRepository.getAllFeedsList()
            val syncResult = ghostwriterRepository.syncFeeds(feeds)

            when (syncResult) {
                is GhostwriterResult.Success -> {
                    Log.i(TAG, "Synced ${syncResult.data.synced} feeds to Ghostwriter")
                }
                is GhostwriterResult.Error -> {
                    Log.w(TAG, "Feed sync warning: ${syncResult.message}")
                    // Continue anyway - feeds may already be synced
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            isGenerating = false,
                            digestFailed = true,
                            ghostwriterError = "Ghostwriter not configured"
                        )
                    }
                    return@launch
                }
            }

            // Trigger digest generation
            val triggerResult = ghostwriterRepository.triggerDigest("manual")

            when (triggerResult) {
                is GhostwriterResult.Success -> {
                    val digestId = triggerResult.data.id
                    if (digestId != null) {
                        // Start polling for status
                        pollDigestStatus(digestId)
                    } else {
                        _uiState.update {
                            it.copy(isGenerating = false, digestFailed = true)
                        }
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isGenerating = false,
                            digestFailed = true,
                            ghostwriterError = triggerResult.message
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            isGenerating = false,
                            digestFailed = true,
                            ghostwriterError = "Ghostwriter not configured"
                        )
                    }
                }
            }
        }
    }

    private fun pollDigestStatus(digestId: String) {
        digestPollingJob?.cancel()
        digestPollingJob = viewModelScope.launch {
            while (true) {
                val statusResult = ghostwriterRepository.getDigestStatus(digestId)

                when (statusResult) {
                    is GhostwriterResult.Success -> {
                        val status = statusResult.data
                        _uiState.update {
                            it.copy(ghostwriterProgress = status)
                        }

                        when (status.status) {
                            "completed" -> {
                                // Download the digest
                                downloadLatestDigest()
                                return@launch
                            }
                            "failed" -> {
                                _uiState.update {
                                    it.copy(
                                        isGenerating = false,
                                        digestFailed = true,
                                        ghostwriterError = "Digest generation failed on server"
                                    )
                                }
                                return@launch
                            }
                            else -> {
                                // Still processing, continue polling
                                delay(2000)
                            }
                        }
                    }
                    is GhostwriterResult.Error -> {
                        Log.e(TAG, "Status polling failed: ${statusResult.message}")
                        delay(3000) // Retry after longer delay
                    }
                    is GhostwriterResult.NotConfigured -> {
                        _uiState.update {
                            it.copy(isGenerating = false, digestFailed = true)
                        }
                        return@launch
                    }
                }
            }
        }
    }

    private suspend fun downloadLatestDigest() {
        val latestResult = ghostwriterRepository.getLatestDigest()

        when (latestResult) {
            is GhostwriterResult.Success -> {
                val downloadResult = ghostwriterRepository.downloadDigest(latestResult.data.filename)

                when (downloadResult) {
                    is GhostwriterResult.Success -> {
                        Log.i(TAG, "Downloaded digest: ${downloadResult.data.absolutePath}")
                        _uiState.update {
                            it.copy(
                                isGenerating = false,
                                digestCompleted = true,
                                ghostwriterProgress = null
                            )
                        }
                    }
                    is GhostwriterResult.Error -> {
                        _uiState.update {
                            it.copy(
                                isGenerating = false,
                                digestFailed = true,
                                ghostwriterError = "Download failed: ${downloadResult.message}"
                            )
                        }
                    }
                    is GhostwriterResult.NotConfigured -> {
                        _uiState.update { it.copy(isGenerating = false, digestFailed = true) }
                    }
                }
            }
            is GhostwriterResult.Error -> {
                _uiState.update {
                    it.copy(
                        isGenerating = false,
                        digestFailed = true,
                        ghostwriterError = latestResult.message
                    )
                }
            }
            is GhostwriterResult.NotConfigured -> {
                _uiState.update { it.copy(isGenerating = false, digestFailed = true) }
            }
        }
    }

    fun clearDigestTriggeredFlag() {
        _uiState.update { it.copy(digestTriggered = false) }
    }

    fun clearDigestCompletedFlag() {
        _uiState.update { it.copy(digestCompleted = false) }
    }

    fun clearDigestFailedFlag() {
        _uiState.update { it.copy(digestFailed = false, ghostwriterError = null) }
    }

    fun clearApiKeySavedFlag() {
        _uiState.update { it.copy(apiKeySaved = false) }
    }

    fun resetAllData() {
        viewModelScope.launch {
            digestRepository.deleteAllDigests()
            feedRepository.resetAllLastFetched()
            _uiState.update { it.copy(dataReset = true) }
        }
    }

    fun clearDataResetFlag() {
        _uiState.update { it.copy(dataReset = false) }
    }

    // ===== Custom Export Directory =====

    fun setCustomExportUri(uri: Uri?) {
        viewModelScope.launch {
            val uriString = uri?.toString()
            settingsRepository.setCustomExportUri(uriString)
            if (uriString != null) {
                settingsRepository.setCustomExportEnabled(true)
            }
            _uiState.update {
                it.copy(
                    customExportUri = uriString,
                    customExportDisplayPath = getDisplayPath(uriString),
                    customExportEnabled = uriString != null
                )
            }
        }
    }

    fun toggleCustomExport(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepository.setCustomExportEnabled(enabled)
            _uiState.update { it.copy(customExportEnabled = enabled) }
        }
    }

    fun clearCustomExportDirectory() {
        viewModelScope.launch {
            settingsRepository.setCustomExportUri(null)
            settingsRepository.setCustomExportEnabled(false)
            _uiState.update {
                it.copy(
                    customExportUri = null,
                    customExportDisplayPath = null,
                    customExportEnabled = false
                )
            }
        }
    }

    private fun getDisplayPath(uriString: String?): String? {
        if (uriString == null) return null
        return try {
            val uri = Uri.parse(uriString)
            // Extract the path portion from the tree URI
            // Format is typically: content://com.android.externalstorage.documents/tree/primary%3APath%2FTo%2FFolder
            val path = uri.lastPathSegment
            if (path != null) {
                // Decode and clean up the path
                val decoded = Uri.decode(path)
                // Remove the "primary:" or similar prefix and show just the path
                decoded.substringAfter(":", decoded).replace("/", " / ")
            } else {
                uriString
            }
        } catch (e: Exception) {
            uriString
        }
    }

    // ===== Ghostwriter Settings =====

    fun updateGhostwriterEnabled(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepository.setGhostwriterEnabled(enabled)
            _uiState.update { it.copy(ghostwriterEnabled = enabled) }

            if (enabled && settingsRepository.isGhostwriterConfigured()) {
                // Cancel local scheduled generation - backend handles it
                digestScheduler.cancelAllPeriods()
                // Start periodic digest sync and perform initial sync
                digestScheduler.scheduleDigestSync()
                digestScheduler.syncDigestsNow()
                performInitialGhostwriterSync()
                refreshMediaOverview()
                refreshLogFiles()
            } else if (!enabled) {
                // Stop periodic digest sync when Ghostwriter is disabled
                digestScheduler.cancelDigestSync()
                // Re-enable local scheduled generation
                digestScheduler.scheduleAllPeriods()
            }
        }
    }

    fun updateGhostwriterUrl(url: String) {
        _uiState.update { it.copy(ghostwriterUrl = url) }
    }

    fun saveGhostwriterUrl() {
        viewModelScope.launch {
            val url = _uiState.value.ghostwriterUrl.trim()
            settingsRepository.setGhostwriterUrl(url.ifBlank { null })
            _uiState.update { it.copy(ghostwriterUrlSaved = true) }
        }
    }

    fun clearGhostwriterUrlSavedFlag() {
        _uiState.update { it.copy(ghostwriterUrlSaved = false) }
    }

    fun updateGhostwriterApiKey(apiKey: String) {
        _uiState.update { it.copy(ghostwriterApiKey = apiKey) }
    }

    fun updateGhostwriterDownloadEpubsOnSync(enabled: Boolean) {
        viewModelScope.launch {
            settingsRepository.setGhostwriterDownloadEpubsOnSync(enabled)
            _uiState.update { it.copy(ghostwriterDownloadEpubsOnSync = enabled) }
        }
    }

    fun saveGhostwriterApiKey() {
        viewModelScope.launch {
            val apiKey = _uiState.value.ghostwriterApiKey.trim()
            settingsRepository.setGhostwriterApiKey(apiKey.ifBlank { null })
            _uiState.update { it.copy(ghostwriterApiKeySaved = true) }
        }
    }

    fun clearGhostwriterApiKeySavedFlag() {
        _uiState.update { it.copy(ghostwriterApiKeySaved = false) }
    }

    fun testGhostwriterConnection() {
        viewModelScope.launch {
            _uiState.update { it.copy(ghostwriterTesting = true, ghostwriterTestResult = null, ghostwriterHealth = null) }

            // Save URL and API key first if changed
            val url = _uiState.value.ghostwriterUrl.trim()
            if (url.isNotBlank()) {
                settingsRepository.setGhostwriterUrl(url)
            }
            val apiKey = _uiState.value.ghostwriterApiKey.trim()
            settingsRepository.setGhostwriterApiKey(apiKey.ifBlank { null })

            val healthResult = ghostwriterRepository.checkHealth()
            val apiKeyPresent = apiKey.isNotBlank()

            val (testResult, connectionSuccessful) = when (healthResult) {
                is GhostwriterResult.Success -> {
                    _uiState.update { it.copy(ghostwriterHealth = healthResult.data) }
                    if (apiKeyPresent) {
                        when (val authResult = ghostwriterRepository.getConfig()) {
                            is GhostwriterResult.Success -> {
                                Pair(
                                    "Connected! Server v${healthResult.data.version}, " +
                                        "AI: ${healthResult.data.aiProvider} (authenticated)",
                                    true
                                )
                            }
                            is GhostwriterResult.Error -> {
                                Pair(formatAuthError(authResult), false)
                            }
                            is GhostwriterResult.NotConfigured -> {
                                Pair("Please enter a server URL", false)
                            }
                        }
                    } else {
                        Pair(
                            "Connected! Server v${healthResult.data.version}, " +
                                "AI: ${healthResult.data.aiProvider} (no token)",
                            true
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    Pair(formatAuthError(healthResult), false)
                }
                is GhostwriterResult.NotConfigured -> {
                    Pair("Please enter a server URL", false)
                }
            }

            _uiState.update {
                it.copy(
                    ghostwriterTesting = false,
                    ghostwriterTestResult = testResult
                )
            }

            // If connection successful, fetch integration status
            if (connectionSuccessful) {
                fetchIntegrationStatus()
                refreshMediaOverview()
                refreshLogFiles()
                refreshAuthTokens()

                // If Ghostwriter is enabled, perform initial sync
                if (_uiState.value.ghostwriterEnabled) {
                    digestScheduler.scheduleDigestSync()
                    digestScheduler.syncDigestsNow()
                    performInitialGhostwriterSync()
                }
            }
        }
    }

    private fun formatAuthError(result: GhostwriterResult.Error): String {
        return when (result.code) {
            401 -> "Authentication failed. Check your API token."
            429 -> "Too many attempts. Please try again in a minute."
            else -> "Error: ${result.message}"
        }
    }

    /**
     * Fetch config-backed settings from Ghostwriter (integrations, media inclusion, covers).
     */
    private fun fetchIntegrationStatus() {
        viewModelScope.launch {
            val result = ghostwriterRepository.getConfig()
            when (result) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        applyConfigResponse(
                            state = it,
                            config = result.data
                        )
                    }
                    settingsRepository.setConfigUpdatedAt(result.data.updatedAt)
                }
                is GhostwriterResult.Error -> {
                    Log.w(TAG, "Failed to fetch integration status: ${result.message}")
                }
                is GhostwriterResult.NotConfigured -> { }
            }
        }
    }

    fun updateIncludePodcastsInDigest(enabled: Boolean) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(includePodcastsInDigest = enabled) },
            rollbackUpdate = { it.copy(includePodcastsInDigest = !enabled) },
            successMessage = if (enabled) {
                "Podcasts will be included in digests"
            } else {
                "Podcasts will be excluded from digests"
            }
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                includePodcastsInDigest = enabled,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateIncludeYoutubeInDigest(enabled: Boolean) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(includeYoutubeInDigest = enabled) },
            rollbackUpdate = { it.copy(includeYoutubeInDigest = !enabled) },
            successMessage = if (enabled) {
                "YouTube items will be included in digests"
            } else {
                "YouTube items will be excluded from digests"
            }
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                includeYoutubeInDigest = enabled,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateCoverEnabled(enabled: Boolean) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(coverEnabled = enabled) },
            rollbackUpdate = { it.copy(coverEnabled = !enabled) },
            successMessage = if (enabled) {
                "AI cover generation enabled"
            } else {
                "AI cover generation disabled"
            }
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                coverEnabled = enabled,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateCoverOverlayEnabled(enabled: Boolean) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(coverOverlayEnabled = enabled) },
            rollbackUpdate = { it.copy(coverOverlayEnabled = !enabled) },
            successMessage = if (enabled) {
                "Cover metadata overlay enabled"
            } else {
                "Cover metadata overlay disabled"
            }
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                coverOverlayEnabled = enabled,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateCoverProvider(provider: String) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(coverProvider = provider) },
            rollbackUpdate = { state ->
                state.copy(coverProvider = if (provider == "nano-banana") "gpt-image-1" else "nano-banana")
            },
            successMessage = "Cover provider updated"
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                coverProvider = provider,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateCoverQuality(quality: String) {
        updateGhostwriterConfig(
            optimisticUpdate = { it.copy(coverQuality = quality) },
            rollbackUpdate = { state ->
                state.copy(coverQuality = when (quality) {
                    "low" -> "medium"
                    "high" -> "medium"
                    else -> "high"
                })
            },
            successMessage = "Cover quality updated"
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                coverQuality = quality,
                clientUpdatedAt = timestamp
            )
        }
    }

    fun updateCoverPrompt(prompt: String) {
        _uiState.update { it.copy(coverPrompt = prompt) }
    }

    fun saveCoverPrompt() {
        val prompt = _uiState.value.coverPrompt
        updateGhostwriterConfig(
            optimisticUpdate = { it },
            rollbackUpdate = { it },
            successMessage = "Cover prompt saved"
        ) { timestamp ->
            ghostwriterRepository.updateConfig(
                coverPrompt = prompt,
                clientUpdatedAt = timestamp
            )
        }
    }

    private fun updateGhostwriterConfig(
        optimisticUpdate: (SettingsUiState) -> SettingsUiState,
        rollbackUpdate: (SettingsUiState) -> SettingsUiState,
        successMessage: String,
        action: suspend (String?) -> GhostwriterResult<ClientConfigResponse>
    ) {
        viewModelScope.launch {
            if (_uiState.value.configActionRunning) {
                return@launch
            }

            _uiState.update {
                optimisticUpdate(it).copy(
                    configActionRunning = true,
                    integrationActionResult = null
                )
            }

            val localUpdatedAt = settingsRepository.getConfigUpdatedAt()
            when (val result = action(localUpdatedAt)) {
                is GhostwriterResult.Success -> {
                    settingsRepository.setConfigUpdatedAt(result.data.updatedAt)
                    _uiState.update {
                        applyConfigResponse(
                            state = it.copy(configActionRunning = false),
                            config = result.data
                        ).copy(integrationActionResult = successMessage)
                    }
                }

                is GhostwriterResult.Error -> {
                    if (result.code == 409) {
                        when (val refetch = ghostwriterRepository.getConfig()) {
                            is GhostwriterResult.Success -> {
                                settingsRepository.setConfigUpdatedAt(refetch.data.updatedAt)
                                _uiState.update {
                                    applyConfigResponse(
                                        state = it.copy(configActionRunning = false),
                                        config = refetch.data
                                    ).copy(
                                        integrationActionResult = "Config changed on server. Refreshed latest values."
                                    )
                                }
                            }

                            else -> {
                                _uiState.update {
                                    rollbackUpdate(it).copy(
                                        configActionRunning = false,
                                        integrationActionResult = "Config changed on server. Please retry."
                                    )
                                }
                            }
                        }
                    } else {
                        _uiState.update {
                            rollbackUpdate(it).copy(
                                configActionRunning = false,
                                integrationActionResult = "Config update failed: ${result.message}"
                            )
                        }
                    }
                }

                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        rollbackUpdate(it).copy(
                            configActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    private fun applyConfigResponse(
        state: SettingsUiState,
        config: ClientConfigResponse
    ): SettingsUiState {
        return state.copy(
            wallabagIntegration = config.wallabag,
            newslettersIntegration = config.newsletters,
            includePodcastsInDigest = config.includePodcastsInDigest ?: state.includePodcastsInDigest,
            includeYoutubeInDigest = config.includeYoutubeInDigest ?: state.includeYoutubeInDigest,
            coverEnabled = config.coverEnabled ?: state.coverEnabled,
            coverOverlayEnabled = config.coverOverlayEnabled ?: state.coverOverlayEnabled,
            coverProvider = config.coverProvider ?: state.coverProvider,
            coverQuality = config.coverQuality ?: state.coverQuality,
            coverPrompt = config.coverPrompt ?: state.coverPrompt
        )
    }

    fun refreshMediaOverview() {
        viewModelScope.launch {
            _uiState.update { it.copy(mediaRefreshing = true) }

            var podcastCount = _uiState.value.podcastFeedCount
            var youtubeCount = _uiState.value.youtubeFeedCount
            var podcastFeeds = _uiState.value.podcastFeeds
            var youtubeFeeds = _uiState.value.youtubeFeeds
            var mediaStatus = _uiState.value.mediaStatus
            var recentMediaItems = _uiState.value.recentMediaItems
            var actionMessage: String? = null

            when (val podcastResult = ghostwriterRepository.getPodcastFeeds()) {
                is GhostwriterResult.Success -> {
                    podcastCount = podcastResult.data.size
                    podcastFeeds = podcastResult.data.map { feed ->
                        MediaFeedUi(
                            id = feed.id,
                            title = feed.title,
                            url = feed.url,
                            feedType = feed.feedType,
                            isActive = feed.isActive,
                            mode = feed.mode,
                            maxItems = feed.maxItems
                        )
                    }
                }
                is GhostwriterResult.Error -> actionMessage = "Failed to load podcast feeds: ${podcastResult.message}"
                is GhostwriterResult.NotConfigured -> actionMessage = "Ghostwriter is not configured"
            }

            when (val youtubeResult = ghostwriterRepository.getYouTubeFeeds()) {
                is GhostwriterResult.Success -> {
                    youtubeCount = youtubeResult.data.size
                    youtubeFeeds = youtubeResult.data.map { feed ->
                        MediaFeedUi(
                            id = feed.id,
                            title = feed.title,
                            url = feed.url,
                            feedType = feed.feedType,
                            isActive = feed.isActive,
                            mode = feed.mode,
                            maxItems = feed.maxItems
                        )
                    }
                }
                is GhostwriterResult.Error -> actionMessage = actionMessage ?: "Failed to load YouTube feeds: ${youtubeResult.message}"
                is GhostwriterResult.NotConfigured -> actionMessage = actionMessage ?: "Ghostwriter is not configured"
            }

            val podcastItems = when (val podcastItemsResult = ghostwriterRepository.getAllPodcastItems()) {
                is GhostwriterResult.Success -> podcastItemsResult.data
                is GhostwriterResult.Error -> {
                    actionMessage = actionMessage ?: "Failed to load podcast items: ${podcastItemsResult.message}"
                    emptyList()
                }
                is GhostwriterResult.NotConfigured -> {
                    actionMessage = actionMessage ?: "Ghostwriter is not configured"
                    emptyList()
                }
            }

            val youtubeItems = when (val youtubeItemsResult = ghostwriterRepository.getAllYouTubeItems()) {
                is GhostwriterResult.Success -> youtubeItemsResult.data
                is GhostwriterResult.Error -> {
                    actionMessage = actionMessage ?: "Failed to load YouTube items: ${youtubeItemsResult.message}"
                    emptyList()
                }
                is GhostwriterResult.NotConfigured -> {
                    actionMessage = actionMessage ?: "Ghostwriter is not configured"
                    emptyList()
                }
            }

            recentMediaItems = (podcastItems + youtubeItems)
                .map { item ->
                    MediaItemUi(
                        id = item.id,
                        title = item.title,
                        author = item.author,
                        contentType = item.contentType,
                        status = item.status,
                        createdAt = item.createdAt
                    )
                }
                .sortedByDescending { it.createdAt }
                .take(8)

            when (val statusResult = ghostwriterRepository.getMediaStatus()) {
                is GhostwriterResult.Success -> mediaStatus = statusResult.data
                is GhostwriterResult.Error -> actionMessage = actionMessage ?: "Failed to load media status: ${statusResult.message}"
                is GhostwriterResult.NotConfigured -> actionMessage = actionMessage ?: "Ghostwriter is not configured"
            }

            _uiState.update {
                it.copy(
                    mediaRefreshing = false,
                    podcastFeedCount = podcastCount,
                    youtubeFeedCount = youtubeCount,
                    podcastFeeds = podcastFeeds,
                    youtubeFeeds = youtubeFeeds,
                    mediaStatus = mediaStatus,
                    recentMediaItems = recentMediaItems,
                    integrationActionResult = actionMessage
                )
            }
        }
    }

    fun triggerMediaProcessing() {
        viewModelScope.launch {
            _uiState.update { it.copy(mediaTriggering = true) }
            when (val result = ghostwriterRepository.triggerMediaProcessing()) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            mediaTriggering = false,
                            integrationActionResult = result.data.detail ?: "Media processing triggered"
                        )
                    }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            mediaTriggering = false,
                            integrationActionResult = "Failed to trigger media processing: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            mediaTriggering = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun refreshLogFiles() {
        viewModelScope.launch {
            _uiState.update { it.copy(logsRefreshing = true) }
            when (val result = ghostwriterRepository.getLogFiles()) {
                is GhostwriterResult.Success -> {
                    val logs = result.data
                        .sortedByDescending { it.modifiedAt }
                        .take(8)
                        .map {
                            LogFileUi(
                                filename = it.filename,
                                sizeBytes = it.sizeBytes,
                                modifiedAt = it.modifiedAt
                            )
                        }
                    _uiState.update {
                        it.copy(
                            logsRefreshing = false,
                            logFiles = logs
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            logsRefreshing = false,
                            integrationActionResult = "Failed to load logs: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            logsRefreshing = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun createPodcastFeed(url: String) {
        val trimmed = url.trim()
        if (trimmed.isBlank()) {
            _uiState.update { it.copy(integrationActionResult = "Podcast URL cannot be empty") }
            return
        }
        viewModelScope.launch {
            when (val result = ghostwriterRepository.createPodcastFeed(url = trimmed, title = trimmed)) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(integrationActionResult = "Podcast feed added: ${result.data.title}")
                    }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(integrationActionResult = "Failed to add podcast feed: ${result.message}")
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun createYouTubeFeed(url: String) {
        val trimmed = url.trim()
        if (trimmed.isBlank()) {
            _uiState.update { it.copy(integrationActionResult = "YouTube URL cannot be empty") }
            return
        }
        viewModelScope.launch {
            val resolved = ghostwriterRepository.resolveYouTubeFeed(trimmed)
            when (resolved) {
                is GhostwriterResult.Success -> {
                    val createResult = ghostwriterRepository.createYouTubeFeed(
                        url = trimmed,
                        resolvedFeedUrl = resolved.data.rssFeedUrl,
                        title = resolved.data.channelTitle ?: trimmed
                    )
                    when (createResult) {
                        is GhostwriterResult.Success -> {
                            _uiState.update {
                                it.copy(integrationActionResult = "YouTube feed added: ${createResult.data.title}")
                            }
                            refreshMediaOverview()
                        }
                        is GhostwriterResult.Error -> {
                            _uiState.update {
                                it.copy(integrationActionResult = "Failed to add YouTube feed: ${createResult.message}")
                            }
                        }
                        is GhostwriterResult.NotConfigured -> {
                            _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                        }
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(integrationActionResult = "Failed to resolve YouTube URL: ${resolved.message}")
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun updateMediaFeedActive(feedType: String, feedId: String, enabled: Boolean) {
        viewModelScope.launch {
            val result = when (feedType.lowercase()) {
                "podcast" -> ghostwriterRepository.updatePodcastFeed(feedId = feedId, isActive = enabled)
                "youtube" -> ghostwriterRepository.updateYouTubeFeed(feedId = feedId, isActive = enabled)
                else -> {
                    _uiState.update { it.copy(integrationActionResult = "Unsupported feed type: $feedType") }
                    return@launch
                }
            }
            when (result) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionResult = "${result.data.title}: ${if (enabled) "Enabled" else "Paused"}"
                        )
                    }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update { it.copy(integrationActionResult = "Failed to update feed: ${result.message}") }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun updateMediaFeedMode(feedType: String, feedId: String, mode: String) {
        viewModelScope.launch {
            val result = when (feedType.lowercase()) {
                "podcast" -> ghostwriterRepository.updatePodcastFeed(feedId = feedId, mode = mode)
                "youtube" -> ghostwriterRepository.updateYouTubeFeed(feedId = feedId, mode = mode)
                else -> {
                    _uiState.update { it.copy(integrationActionResult = "Unsupported feed type: $feedType") }
                    return@launch
                }
            }
            when (result) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionResult = "${result.data.title}: mode set to $mode"
                        )
                    }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update { it.copy(integrationActionResult = "Failed to update feed mode: ${result.message}") }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun updateMediaFeedMaxItems(feedType: String, feedId: String, maxItems: Int) {
        viewModelScope.launch {
            val safeMax = maxItems.coerceIn(1, 50)
            val result = when (feedType.lowercase()) {
                "podcast" -> ghostwriterRepository.updatePodcastFeed(feedId = feedId, maxItems = safeMax)
                "youtube" -> ghostwriterRepository.updateYouTubeFeed(feedId = feedId, maxItems = safeMax)
                else -> {
                    _uiState.update { it.copy(integrationActionResult = "Unsupported feed type: $feedType") }
                    return@launch
                }
            }
            when (result) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(integrationActionResult = "${result.data.title}: max items set to $safeMax")
                    }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update { it.copy(integrationActionResult = "Failed to update max items: ${result.message}") }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun deleteMediaFeed(feedType: String, feedId: String) {
        viewModelScope.launch {
            val result = when (feedType.lowercase()) {
                "podcast" -> ghostwriterRepository.deletePodcastFeed(feedId)
                "youtube" -> ghostwriterRepository.deleteYouTubeFeed(feedId)
                else -> {
                    _uiState.update { it.copy(integrationActionResult = "Unsupported feed type: $feedType") }
                    return@launch
                }
            }
            when (result) {
                is GhostwriterResult.Success -> {
                    _uiState.update { it.copy(integrationActionResult = result.data.message ?: "Feed deleted") }
                    refreshMediaOverview()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update { it.copy(integrationActionResult = "Failed to delete feed: ${result.message}") }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(integrationActionResult = "Ghostwriter is not configured") }
                }
            }
        }
    }

    fun loadMediaItemDetail(itemId: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(mediaItemDetailLoading = true, mediaItemDetail = null) }
            when (val result = ghostwriterRepository.getMediaItem(itemId)) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            mediaItemDetailLoading = false,
                            mediaItemDetail = MediaItemDetailUi(
                                id = result.data.id,
                                title = result.data.title,
                                author = result.data.author,
                                contentType = result.data.contentType,
                                status = result.data.status,
                                mode = result.data.mode,
                                wordCount = result.data.wordCount,
                                isSummary = result.data.isSummary,
                                content = result.data.content,
                                contentHtml = result.data.contentHtml,
                                errorMessage = result.data.errorMessage,
                                url = result.data.url,
                                createdAt = result.data.createdAt,
                                completedAt = result.data.completedAt
                            )
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            mediaItemDetailLoading = false,
                            integrationActionResult = "Failed to load media item: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            mediaItemDetailLoading = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun clearMediaItemDetail() {
        _uiState.update { it.copy(mediaItemDetail = null) }
    }

    fun refreshAuthTokens() {
        viewModelScope.launch {
            _uiState.update { it.copy(authTokensLoading = true) }
            when (val result = ghostwriterRepository.listAuthTokens()) {
                is GhostwriterResult.Success -> {
                    val tokens = result.data.map { token ->
                        AuthTokenUi(
                            id = token.id,
                            name = token.name,
                            tokenPrefix = token.tokenPrefix,
                            createdAt = token.createdAt,
                            lastUsedAt = token.lastUsedAt
                        )
                    }
                    _uiState.update {
                        it.copy(
                            authTokensLoading = false,
                            authTokens = tokens
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            authTokensLoading = false,
                            integrationActionResult = "Failed to load auth tokens: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            authTokensLoading = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun updateAuthTokenCreateName(name: String) {
        _uiState.update { it.copy(authTokenCreateName = name) }
    }

    fun createAuthToken() {
        viewModelScope.launch {
            val name = _uiState.value.authTokenCreateName.trim()
            if (name.isBlank()) {
                _uiState.update { it.copy(integrationActionResult = "Token name cannot be empty") }
                return@launch
            }
            _uiState.update { it.copy(authTokensActionRunning = true) }
            when (val result = ghostwriterRepository.createAuthToken(name)) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            authTokenCreateName = "",
                            newlyCreatedAuthToken = result.data.token,
                            integrationActionResult = "Token created: ${result.data.tokenPrefix}"
                        )
                    }
                    refreshAuthTokens()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            integrationActionResult = "Failed to create token: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun revokeAuthToken(tokenId: String) {
        viewModelScope.launch {
            _uiState.update { it.copy(authTokensActionRunning = true) }
            when (val result = ghostwriterRepository.revokeAuthToken(tokenId)) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            integrationActionResult = result.data.message ?: "Token revoked"
                        )
                    }
                    refreshAuthTokens()
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            integrationActionResult = "Failed to revoke token: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            authTokensActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun clearNewlyCreatedAuthToken() {
        _uiState.update { it.copy(newlyCreatedAuthToken = null) }
    }

    fun clearGhostwriterTestResult() {
        _uiState.update { it.copy(ghostwriterTestResult = null) }
    }

    fun clearGhostwriterSyncResult() {
        _uiState.update { it.copy(ghostwriterSyncResult = null) }
    }

    fun previewWallabag() {
        viewModelScope.launch {
            _uiState.update { it.copy(integrationActionRunning = true, integrationActionResult = null) }
            when (val result = ghostwriterRepository.previewWallabag()) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = formatPreviewResult("Wallabag", result.data)
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Wallabag preview failed: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun previewNewsletters() {
        viewModelScope.launch {
            _uiState.update { it.copy(integrationActionRunning = true, integrationActionResult = null) }
            when (val result = ghostwriterRepository.previewNewsletters()) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = formatPreviewResult("Newsletters", result.data)
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Newsletter preview failed: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun clearWallabagSeen() {
        viewModelScope.launch {
            _uiState.update { it.copy(integrationActionRunning = true, integrationActionResult = null) }
            when (val result = ghostwriterRepository.clearWallabagSeen()) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Cleared ${result.data.cleared} Wallabag seen markers"
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Failed to clear Wallabag seen markers: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun clearNewslettersSeen() {
        viewModelScope.launch {
            _uiState.update { it.copy(integrationActionRunning = true, integrationActionResult = null) }
            when (val result = ghostwriterRepository.clearNewsletterSeen()) {
                is GhostwriterResult.Success -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Cleared ${result.data.cleared} newsletter seen markers"
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Failed to clear newsletter seen markers: ${result.message}"
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update {
                        it.copy(
                            integrationActionRunning = false,
                            integrationActionResult = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    fun clearIntegrationActionResult() {
        _uiState.update { it.copy(integrationActionResult = null) }
    }

    private fun formatPreviewResult(sourceName: String, response: com.example.epilogue.data.remote.ghostwriter.PreviewResponse): String {
        return if (response.status == "ok") {
            "$sourceName preview: ${response.count} article${if (response.count == 1) "" else "s"} available"
        } else {
            response.detail ?: "$sourceName preview failed"
        }
    }

    /**
     * Perform initial sync to Ghostwriter when first enabled.
     * Syncs feeds and schedule preferences.
     */
    private fun performInitialGhostwriterSync() {
        viewModelScope.launch {
            _uiState.update { it.copy(ghostwriterSyncing = true, ghostwriterSyncResult = null) }

            var syncStatus = mutableListOf<String>()
            var hasError = false

            // 1. Sync feeds
            val feeds = feedRepository.getAllFeedsList()
            if (feeds.isNotEmpty()) {
                val feedResult = ghostwriterRepository.syncFeeds(feeds)
                when (feedResult) {
                    is GhostwriterResult.Success -> {
                        syncStatus.add("${feedResult.data.synced} feeds synced")
                        Log.i(TAG, "Initial sync: ${feedResult.data.synced} feeds synced")
                    }
                    is GhostwriterResult.Error -> {
                        syncStatus.add("Feed sync failed")
                        hasError = true
                        Log.e(TAG, "Initial sync: feed sync failed: ${feedResult.message}")
                    }
                    is GhostwriterResult.NotConfigured -> {
                        hasError = true
                    }
                }
            } else {
                syncStatus.add("No feeds to sync")
            }

            // 2. Sync schedule preferences
            val selectedPeriods = _uiState.value.selectedPeriods
            val scheduleSyncResults = mutableListOf<String>()

            for (period in DigestPeriod.entries) {
                val enabled = period in selectedPeriods
                val scheduleResult = ghostwriterRepository.updateSchedule(
                    period = period.name.lowercase(),
                    enabled = enabled
                )
                when (scheduleResult) {
                    is GhostwriterResult.Success -> {
                        if (enabled) {
                            scheduleSyncResults.add(period.name.lowercase())
                        }
                    }
                    is GhostwriterResult.Error -> {
                        Log.w(TAG, "Failed to sync schedule for ${period.name}: ${scheduleResult.message}")
                    }
                    is GhostwriterResult.NotConfigured -> { }
                }
            }

            if (scheduleSyncResults.isNotEmpty()) {
                syncStatus.add("Schedules: ${scheduleSyncResults.joinToString(", ")}")
            }

            // 3. Send initial heartbeat
            val heartbeatResult = ghostwriterRepository.sendHeartbeat()
            when (heartbeatResult) {
                is GhostwriterResult.Success -> {
                    Log.i(TAG, "Initial sync: heartbeat sent")
                }
                is GhostwriterResult.Error -> {
                    Log.w(TAG, "Initial sync: heartbeat failed: ${heartbeatResult.message}")
                }
                is GhostwriterResult.NotConfigured -> { }
            }

            val resultMessage = if (hasError) {
                "Sync completed with errors"
            } else {
                syncStatus.joinToString(". ")
            }

            _uiState.update {
                it.copy(
                    ghostwriterSyncing = false,
                    ghostwriterSyncResult = resultMessage
                )
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        digestPollingJob?.cancel()
    }
}

data class SettingsUiState(
    val apiKey: String = "",
    val apiKeySaved: Boolean = false,
    val selectedPeriods: Set<DigestPeriod> = setOf(DigestPeriod.EVENING),
    val minWordCount: Int = 0,
    val einkMode: Boolean = false,
    val isGenerating: Boolean = false,
    val digestTriggered: Boolean = false,
    val digestCompleted: Boolean = false,
    val digestFailed: Boolean = false,
    val dataReset: Boolean = false,
    val customExportUri: String? = null,
    val customExportEnabled: Boolean = false,
    val customExportDisplayPath: String? = null,
    // Ghostwriter settings
    val ghostwriterEnabled: Boolean = false,
    val ghostwriterDownloadEpubsOnSync: Boolean = true,
    val ghostwriterUrl: String = "",
    val ghostwriterUrlSaved: Boolean = false,
    val ghostwriterApiKey: String = "",
    val ghostwriterApiKeySaved: Boolean = false,
    val ghostwriterTesting: Boolean = false,
    val ghostwriterTestResult: String? = null,
    val ghostwriterProgress: DigestStatusResponse? = null,
    val ghostwriterError: String? = null,
    val ghostwriterSyncing: Boolean = false,
    val ghostwriterSyncResult: String? = null,
    val configActionRunning: Boolean = false,
    val includePodcastsInDigest: Boolean = true,
    val includeYoutubeInDigest: Boolean = true,
    val coverEnabled: Boolean = false,
    val coverOverlayEnabled: Boolean = true,
    val coverProvider: String = "gpt-image-1",
    val coverQuality: String = "medium",
    val coverPrompt: String = "",
    val integrationActionRunning: Boolean = false,
    val integrationActionResult: String? = null,
    val mediaRefreshing: Boolean = false,
    val mediaTriggering: Boolean = false,
    val podcastFeedCount: Int = 0,
    val youtubeFeedCount: Int = 0,
    val podcastFeeds: List<MediaFeedUi> = emptyList(),
    val youtubeFeeds: List<MediaFeedUi> = emptyList(),
    val mediaStatus: MediaProcessingStatusResponse? = null,
    val recentMediaItems: List<MediaItemUi> = emptyList(),
    val mediaItemDetailLoading: Boolean = false,
    val mediaItemDetail: MediaItemDetailUi? = null,
    val authTokensLoading: Boolean = false,
    val authTokensActionRunning: Boolean = false,
    val authTokens: List<AuthTokenUi> = emptyList(),
    val authTokenCreateName: String = "",
    val newlyCreatedAuthToken: String? = null,
    val logsRefreshing: Boolean = false,
    val logFiles: List<LogFileUi> = emptyList(),
    val ghostwriterHealth: HealthResponse? = null,
    // Integration status
    val wallabagIntegration: IntegrationStatus? = null,
    val newslettersIntegration: IntegrationStatus? = null,
    val serverSchedule: SettingsRepository.GhostwriterSchedule? = null
)

data class MediaItemUi(
    val id: String,
    val title: String,
    val author: String?,
    val contentType: String,
    val status: String,
    val createdAt: String
)

data class MediaFeedUi(
    val id: String,
    val title: String,
    val url: String,
    val feedType: String,
    val isActive: Boolean,
    val mode: String,
    val maxItems: Int
)

data class MediaItemDetailUi(
    val id: String,
    val title: String,
    val author: String?,
    val contentType: String,
    val status: String,
    val mode: String,
    val wordCount: Int,
    val isSummary: Boolean,
    val content: String,
    val contentHtml: String?,
    val errorMessage: String?,
    val url: String,
    val createdAt: String,
    val completedAt: String?
)

data class AuthTokenUi(
    val id: String,
    val name: String,
    val tokenPrefix: String,
    val createdAt: String,
    val lastUsedAt: String?
)

data class LogFileUi(
    val filename: String,
    val sizeBytes: Long,
    val modifiedAt: String
)
