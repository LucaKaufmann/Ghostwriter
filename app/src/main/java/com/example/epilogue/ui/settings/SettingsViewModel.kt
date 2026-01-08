package com.example.epilogue.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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
    private val digestScheduler: DigestScheduler
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    init {
        loadSettings()
    }

    private fun loadSettings() {
        _uiState.update { state ->
            state.copy(
                apiKey = settingsRepository.getOpenAIApiKey() ?: "",
                scheduleHour = settingsRepository.getScheduleHour(),
                scheduleMinute = settingsRepository.getScheduleMinute(),
                minWordCount = settingsRepository.getMinWordCount()
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

    fun runDigestNow() {
        _uiState.update { it.copy(isGenerating = true) }
        digestScheduler.runNow(fetchAll = false)
        // Note: In a real app, you'd observe WorkInfo to track completion
        viewModelScope.launch {
            kotlinx.coroutines.delay(1000)
            _uiState.update { it.copy(isGenerating = false, digestTriggered = true) }
        }
    }

    fun clearDigestTriggeredFlag() {
        _uiState.update { it.copy(digestTriggered = false) }
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
}

data class SettingsUiState(
    val apiKey: String = "",
    val apiKeySaved: Boolean = false,
    val scheduleHour: Int = 22,
    val scheduleMinute: Int = 0,
    val minWordCount: Int = 0,
    val showTimePicker: Boolean = false,
    val isGenerating: Boolean = false,
    val digestTriggered: Boolean = false
)
