package com.example.epilogue.ui.history

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.service.DigestScheduler
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * ViewModel for the digest history screen.
 */
@HiltViewModel
class HistoryViewModel @Inject constructor(
    private val digestRepository: DigestRepository,
    private val digestScheduler: DigestScheduler,
    @ApplicationContext private val context: Context
) : ViewModel() {

    /**
     * All digests ordered by most recent first.
     */
    val digests: StateFlow<List<Digest>> = digestRepository.getAllDigests()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = emptyList()
        )

    private val _uiState = MutableStateFlow(HistoryUiState())
    val uiState: StateFlow<HistoryUiState> = _uiState.asStateFlow()

    /**
     * Show the delete confirmation dialog for a digest.
     */
    fun showDeleteConfirmation(digest: Digest) {
        _uiState.update { it.copy(digestToDelete = digest) }
    }

    /**
     * Dismiss the delete confirmation dialog.
     */
    fun dismissDeleteConfirmation() {
        _uiState.update { it.copy(digestToDelete = null) }
    }

    /**
     * Confirm deletion of the digest.
     */
    fun confirmDelete() {
        val digest = _uiState.value.digestToDelete ?: return
        viewModelScope.launch {
            digestRepository.deleteDigest(digest)
            _uiState.update { it.copy(digestToDelete = null) }
        }
    }

    /**
     * Open the digest EPUB in an external reader app.
     */
    fun openInExternalReader(digest: Digest) {
        val file = File(digest.epubFilePath)
        if (!file.exists()) {
            _uiState.update { it.copy(error = "EPUB file not found") }
            return
        }

        try {
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file
            )

            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/epub+zip")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }

            context.startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            _uiState.update { it.copy(error = "No app found to open EPUB files") }
        } catch (e: Exception) {
            _uiState.update { it.copy(error = "Failed to open file: ${e.message}") }
        }
    }

    /**
     * Clear any error message.
     */
    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * Refresh digests from Ghostwriter.
     * Triggers a sync and shows a brief loading indicator.
     */
    fun refresh() {
        viewModelScope.launch {
            _uiState.update { it.copy(isRefreshing = true) }

            // Trigger digest sync from Ghostwriter
            digestScheduler.syncDigestsNow()

            // Give the sync worker a moment to start and complete
            // The actual digest list updates via Flow from the database
            delay(2000)

            _uiState.update { it.copy(isRefreshing = false) }
        }
    }
}

/**
 * UI state for the history screen.
 */
data class HistoryUiState(
    val digestToDelete: Digest? = null,
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null
)
