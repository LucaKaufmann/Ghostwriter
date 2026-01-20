package com.example.epilogue.ui.settings

import android.net.Uri
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import com.example.epilogue.data.remote.ghostwriter.DigestStatusResponse
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.DigestPeriod
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
    private val ghostwriterRepository: GhostwriterRepository
) : ViewModel() {

    companion object {
        private const val TAG = "SettingsViewModel"
    }

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    private var digestPollingJob: Job? = null

    init {
        loadSettings()
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
                ghostwriterApiKey = settingsRepository.getGhostwriterApiKey() ?: ""
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
        }
    }

    fun updateMinWordCount(count: Int) {
        viewModelScope.launch {
            settingsRepository.setMinWordCount(count)
            _uiState.update { it.copy(minWordCount = count) }
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
            _uiState.update { it.copy(ghostwriterTesting = true, ghostwriterTestResult = null) }

            // Save URL first if changed
            val url = _uiState.value.ghostwriterUrl.trim()
            if (url.isNotBlank()) {
                settingsRepository.setGhostwriterUrl(url)
            }

            val result = ghostwriterRepository.checkHealth()

            val testResult = when (result) {
                is GhostwriterResult.Success -> {
                    "Connected! Server v${result.data.version}, AI: ${result.data.aiProvider}"
                }
                is GhostwriterResult.Error -> {
                    "Error: ${result.message}"
                }
                is GhostwriterResult.NotConfigured -> {
                    "Please enter a server URL"
                }
            }

            _uiState.update {
                it.copy(
                    ghostwriterTesting = false,
                    ghostwriterTestResult = testResult
                )
            }
        }
    }

    fun clearGhostwriterTestResult() {
        _uiState.update { it.copy(ghostwriterTestResult = null) }
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
    val ghostwriterUrl: String = "",
    val ghostwriterUrlSaved: Boolean = false,
    val ghostwriterApiKey: String = "",
    val ghostwriterApiKeySaved: Boolean = false,
    val ghostwriterTesting: Boolean = false,
    val ghostwriterTestResult: String? = null,
    val ghostwriterProgress: DigestStatusResponse? = null,
    val ghostwriterError: String? = null
)
