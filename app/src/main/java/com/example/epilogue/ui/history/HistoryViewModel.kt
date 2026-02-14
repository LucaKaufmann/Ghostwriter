package com.example.epilogue.ui.history

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.GhostwriterRepository.GhostwriterResult
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.service.DigestScheduler
import com.example.epilogue.service.EpubExporter
import com.example.epilogue.service.ExportResult
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
    private val ghostwriterRepository: GhostwriterRepository,
    private val digestScheduler: DigestScheduler,
    private val epubExporter: EpubExporter,
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
            val message = if (digest.isFromGhostwriter) {
                "EPUB not downloaded yet. Use Download in history first."
            } else {
                "EPUB file not found"
            }
            _uiState.update { it.copy(error = message) }
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
     * Share the digest EPUB via system share sheet.
     */
    fun shareDigest(digest: Digest) {
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

            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "application/epub+zip"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }

            context.startActivity(Intent.createChooser(intent, "Share EPUB"))
        } catch (e: ActivityNotFoundException) {
            _uiState.update { it.copy(error = "No app found to share EPUB files") }
        } catch (e: Exception) {
            _uiState.update { it.copy(error = "Failed to share file: ${e.message}") }
        }
    }

    /**
     * Clear any error message.
     */
    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * Download a synced Ghostwriter digest EPUB on demand.
     */
    fun downloadEpub(digest: Digest) {
        if (!digest.isFromGhostwriter) {
            _uiState.update { it.copy(error = "Only Ghostwriter digests can be downloaded") }
            return
        }
        if (_uiState.value.downloadingDigestIds.contains(digest.id)) {
            return
        }

        val filename = digest.epubFilePath.takeIf { it.isNotBlank() }?.let { File(it).name }
        if (filename.isNullOrBlank()) {
            _uiState.update { it.copy(error = "Missing digest filename for download") }
            return
        }

        viewModelScope.launch {
            _uiState.update { it.copy(downloadingDigestIds = it.downloadingDigestIds + digest.id) }

            when (val result = ghostwriterRepository.downloadDigest(filename)) {
                is GhostwriterResult.Success -> {
                    val file = result.data
                    digestRepository.updateDigestEpubPath(digest.id, file.absolutePath)
                    when (val exportResult = epubExporter.exportToCustomDirectory(file)) {
                        is ExportResult.Success -> Unit
                        is ExportResult.PermissionRevoked -> {
                            _uiState.update { it.copy(error = "Custom export permission revoked") }
                        }
                        is ExportResult.Error -> {
                            _uiState.update { it.copy(error = "Custom export failed: ${exportResult.message}") }
                        }
                        ExportResult.NotConfigured -> Unit
                    }
                }
                is GhostwriterResult.Error -> {
                    _uiState.update { it.copy(error = "Download failed: ${result.message}") }
                }
                is GhostwriterResult.NotConfigured -> {
                    _uiState.update { it.copy(error = "Ghostwriter is not configured") }
                }
            }

            _uiState.update { it.copy(downloadingDigestIds = it.downloadingDigestIds - digest.id) }
        }
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
    val downloadingDigestIds: Set<Long> = emptySet(),
    val error: String? = null
)
