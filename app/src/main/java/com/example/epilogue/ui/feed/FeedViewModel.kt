package com.example.epilogue.ui.feed

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.remote.ghostwriter.FeedResponse
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.FeedCorrectionEdits
import com.example.epilogue.data.local.FeedMutationEntity
import com.example.epilogue.data.local.FeedSyncStateEntity
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.ghostwriter.isFeedUrlV2
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
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
    private val feedV2Store: AndroidFeedV2Store,
    private val feedSyncV2UseCase: FeedSyncV2UseCase
) : ViewModel() {

    val feeds: StateFlow<List<Feed>> = feedRepository.getAllFeeds()
        .map { feeds -> feeds.filter { !it.url.startsWith("synthetic://") } }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )

    val unresolved: StateFlow<List<FeedMutationEntity>> = feedV2Store.unresolved()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())
    val syncState: StateFlow<FeedSyncStateEntity?> = feedV2Store.status()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    private val _uiState = MutableStateFlow(FeedUiState())
    val uiState: StateFlow<FeedUiState> = _uiState

    fun addFeed(
        url: String,
        name: String,
        mode: ProcessingMode,
        maxArticles: Int = 0,
        isEnabled: Boolean = true
    ) {
        val trimmedUrl = url.trim()
        val trimmedName = name.trim()
        if (!isFeedUrlV2(trimmedUrl) || trimmedName.isBlank() || maxArticles < 0) {
            _uiState.value = _uiState.value.copy(error = "Enter a valid HTTP or HTTPS feed URL and nickname")
            return
        }
        viewModelScope.launch {
            val feed = Feed(
                url = trimmedUrl,
                name = trimmedName,
                mode = mode,
                maxArticles = maxArticles,
                isEnabled = isEnabled
            )
            try {
                feedRepository.insertFeed(feed)
                _uiState.value = _uiState.value.copy(showAddDialog = false, error = null)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                _uiState.value = _uiState.value.copy(error = error.message ?: "Could not save feed")
            }
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

    fun resolve(opId: String, action: String) {
        viewModelScope.launch {
            if (action == "correct") {
                val refreshed = feedSyncV2UseCase.sync().also { feedV2Store.recordOutcome(it) }
                if (refreshed is FeedSyncV2Outcome.Failed || refreshed is FeedSyncV2Outcome.ServerChanged ||
                    refreshed is FeedSyncV2Outcome.ServerUpgradeRequired) {
                    _uiState.value = _uiState.value.copy(error = "Refresh server state before correcting this feed")
                    return@launch
                }
            }
            if (!feedV2Store.resolve(opId, action)) {
                _uiState.value = _uiState.value.copy(error = "Feed proposal changed; refresh and try again")
                return@launch
            }
            when (val outcome = feedSyncV2UseCase.sync().also { feedV2Store.recordOutcome(it) }) {
                is FeedSyncV2Outcome.Failed -> _uiState.value = _uiState.value.copy(error = outcome.message)
                FeedSyncV2Outcome.ServerChanged -> _uiState.value = _uiState.value.copy(error = "Server changed; resolve the binding before syncing")
                FeedSyncV2Outcome.ServerUpgradeRequired -> _uiState.value = _uiState.value.copy(error = "Server upgrade required for feed sync")
                else -> Unit
            }
        }
    }

    fun correctRejected(opId: String, edits: FeedCorrectionEdits) {
        viewModelScope.launch {
            val refreshed = feedSyncV2UseCase.sync().also { feedV2Store.recordOutcome(it) }
            if (refreshed is FeedSyncV2Outcome.Failed || refreshed is FeedSyncV2Outcome.ServerChanged ||
                refreshed is FeedSyncV2Outcome.ServerUpgradeRequired) {
                _uiState.value = _uiState.value.copy(error = "Refresh server state before correcting this feed")
                return@launch
            }
            if (!feedV2Store.correctRejected(opId, edits.copy(title = edits.title?.trim()))) {
                _uiState.value = _uiState.value.copy(error = "Could not correct this proposal")
                return@launch
            }
            feedV2Store.recordOutcome(feedSyncV2UseCase.sync())
        }
    }

    /** Legacy endpoint is read only and its result never enters Room v2 state. */
    fun previewOlderServerFeeds() {
        viewModelScope.launch {
            when (val result = ghostwriterRepository.getFeedChanges(null)) {
                is GhostwriterRepository.GhostwriterResult.Success ->
                    _uiState.value = _uiState.value.copy(olderServerPreview = result.data.feeds,
                        error = null)
                is GhostwriterRepository.GhostwriterResult.Error ->
                    _uiState.value = _uiState.value.copy(error = result.message)
                GhostwriterRepository.GhostwriterResult.NotConfigured ->
                    _uiState.value = _uiState.value.copy(error = "Ghostwriter is not configured")
            }
        }
    }

    fun reviewChangedServer() {
        viewModelScope.launch {
            if (!feedV2Store.prepareServerReconciliation()) {
                _uiState.value = _uiState.value.copy(error = "Server binding is not paused")
                return@launch
            }
            feedV2Store.recordOutcome(feedSyncV2UseCase.sync())
        }
    }

    fun showAddDialog() {
        _uiState.value = _uiState.value.copy(showAddDialog = true, error = null)
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
    val error: String? = null,
    val olderServerPreview: List<FeedResponse> = emptyList()
)
