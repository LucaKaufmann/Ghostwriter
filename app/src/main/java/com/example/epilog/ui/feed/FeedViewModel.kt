package com.example.epilog.ui.feed

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilog.data.repository.FeedRepository
import com.example.epilog.domain.model.Feed
import com.example.epilog.domain.model.ProcessingMode
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class FeedViewModel @Inject constructor(
    private val feedRepository: FeedRepository
) : ViewModel() {

    val feeds: StateFlow<List<Feed>> = feedRepository.getAllFeeds()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )

    private val _uiState = MutableStateFlow(FeedUiState())
    val uiState: StateFlow<FeedUiState> = _uiState

    fun addFeed(url: String, name: String, mode: ProcessingMode, maxArticles: Int = 0) {
        viewModelScope.launch {
            val feed = Feed(
                url = url.trim(),
                name = name.trim(),
                mode = mode,
                maxArticles = maxArticles
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
            feedRepository.deleteFeed(feed)
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
