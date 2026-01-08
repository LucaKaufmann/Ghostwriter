package com.example.epilogue.ui.settings

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkInfo
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.service.DigestScheduler
import dagger.hilt.android.lifecycle.HiltViewModel
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
    private val feedRepository: FeedRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    init {
        loadSettings()
    }

    private fun loadSettings() {
        val customExportUri = settingsRepository.getCustomExportUri()
        _uiState.update { state ->
            state.copy(
                apiKey = settingsRepository.getOpenAIApiKey() ?: "",
                scheduleHour = settingsRepository.getScheduleHour(),
                scheduleMinute = settingsRepository.getScheduleMinute(),
                minWordCount = settingsRepository.getMinWordCount(),
                einkMode = settingsRepository.getEinkMode(),
                customExportUri = customExportUri,
                customExportEnabled = settingsRepository.isCustomExportEnabled(),
                customExportDisplayPath = getDisplayPath(customExportUri)
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

    fun updateScheduleTime(hour: Int, minute: Int) {
        viewModelScope.launch {
            digestScheduler.updateScheduleTime(hour, minute)
            _uiState.update { state ->
                state.copy(
                    scheduleHour = hour,
                    scheduleMinute = minute
                )
            }
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

    fun clearDigestTriggeredFlag() {
        _uiState.update { it.copy(digestTriggered = false) }
    }

    fun clearDigestCompletedFlag() {
        _uiState.update { it.copy(digestCompleted = false) }
    }

    fun clearDigestFailedFlag() {
        _uiState.update { it.copy(digestFailed = false) }
    }

    fun clearApiKeySavedFlag() {
        _uiState.update { it.copy(apiKeySaved = false) }
    }

    fun showTimePicker() {
        _uiState.update { it.copy(showTimePicker = true) }
    }

    fun hideTimePicker() {
        _uiState.update { it.copy(showTimePicker = false) }
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
}

data class SettingsUiState(
    val apiKey: String = "",
    val apiKeySaved: Boolean = false,
    val scheduleHour: Int = 22,
    val scheduleMinute: Int = 0,
    val minWordCount: Int = 0,
    val einkMode: Boolean = false,
    val showTimePicker: Boolean = false,
    val isGenerating: Boolean = false,
    val digestTriggered: Boolean = false,
    val digestCompleted: Boolean = false,
    val digestFailed: Boolean = false,
    val dataReset: Boolean = false,
    val customExportUri: String? = null,
    val customExportEnabled: Boolean = false,
    val customExportDisplayPath: String? = null
)
