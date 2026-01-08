package com.example.epilogue.ui.history

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.DigestArticle
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

/**
 * ViewModel for the digest detail screen.
 */
@HiltViewModel
class DigestDetailViewModel @Inject constructor(
    private val digestRepository: DigestRepository,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(DigestDetailUiState())
    val uiState: StateFlow<DigestDetailUiState> = _uiState.asStateFlow()

    /**
     * Load the digest and its articles.
     */
    fun loadDigest(digestId: Long) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            try {
                val digest = digestRepository.getDigestById(digestId)
                val articles = digestRepository.getArticlesForDigest(digestId)
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        digest = digest,
                        articles = articles
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, error = e.message ?: "Failed to load digest")
                }
            }
        }
    }

    /**
     * Open the digest EPUB in an external reader app.
     */
    fun openInExternalReader() {
        val digest = _uiState.value.digest ?: return
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
}

/**
 * UI state for the digest detail screen.
 */
data class DigestDetailUiState(
    val isLoading: Boolean = false,
    val digest: Digest? = null,
    val articles: List<DigestArticle> = emptyList(),
    val error: String? = null
)
