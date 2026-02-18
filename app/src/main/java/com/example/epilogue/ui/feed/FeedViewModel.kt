package com.example.epilogue.ui.feed

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class FeedViewModel @Inject constructor(
    private val feedRepository: FeedRepository,
    private val ghostwriterRepository: GhostwriterRepository,
    private val settingsRepository: SettingsRepository
) : ViewModel() {

    companion object {
        private const val TAG = "FeedViewModel"
    }

    val feeds: StateFlow<List<Feed>> = feedRepository.getAllFeeds()
        .map { feeds -> feeds.filter { !it.url.startsWith("synthetic://") } }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )

    private val _uiState = MutableStateFlow(FeedUiState())
    val uiState: StateFlow<FeedUiState> = _uiState

    fun addFeed(
        url: String,
        name: String,
        mode: ProcessingMode,
        maxArticles: Int = 0,
        isEnabled: Boolean = true
    ) {
        viewModelScope.launch {
            val feed = Feed(
                url = url.trim(),
                name = name.trim(),
                mode = mode,
                maxArticles = maxArticles,
                isEnabled = isEnabled
            )
            feedRepository.insertFeed(feed)
        }
    }

    fun updateFeed(feed: Feed) {
        viewModelScope.launch {
            feedRepository.updateFeed(feed)
        }
    }

    fun deleteFeed(feed: Feed) {
        viewModelScope.launch {
            // Delete locally
            feedRepository.deleteFeed(feed)

            // Also delete on Ghostwriter if enabled
            if (settingsRepository.isGhostwriterConfigured()) {
                val result = ghostwriterRepository.deleteFeedByUrl(feed.url)
                when (result) {
                    is GhostwriterRepository.GhostwriterResult.Success -> {
                        Log.i(TAG, "Feed deleted on Ghostwriter: ${feed.name}")
                    }
                    is GhostwriterRepository.GhostwriterResult.Error -> {
                        Log.w(TAG, "Failed to delete feed on Ghostwriter: ${result.message}")
                    }
                    is GhostwriterRepository.GhostwriterResult.NotConfigured -> {
                        // Ignore - Ghostwriter not configured
                    }
                }
            }
        }
    }

    fun showAddDialog() {
        _uiState.value = _uiState.value.copy(showAddDialog = true)
    }

    fun hideAddDialog() {
        _uiState.value = _uiState.value.copy(showAddDialog = false)
    }

    fun showEditDialog(feed: Feed) {
        _uiState.value = _uiState.value.copy(editingFeed = feed)
    }

    fun hideEditDialog() {
        _uiState.value = _uiState.value.copy(editingFeed = null)
    }
}

data class FeedUiState(
    val showAddDialog: Boolean = false,
    val editingFeed: Feed? = null,
    val isLoading: Boolean = false,
    val error: String? = null
)
