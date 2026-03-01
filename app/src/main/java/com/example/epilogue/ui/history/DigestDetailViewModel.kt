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
import com.example.epilogue.data.remote.ghostwriter.DigestArticleResponse
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
    private val ghostwriterRepository: GhostwriterRepository,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(DigestDetailUiState())
    val uiState: StateFlow<DigestDetailUiState> = _uiState.asStateFlow()

    private val remoteArticleIdByLocalId = mutableMapOf<Long, String>()
    private val remoteDigestArticlesCache = mutableMapOf<String, List<DigestArticleResponse>>()
    private var lastRemoteArticlesError: String? = null

    /**
     * Load the digest and its articles.
     */
    fun loadDigest(digestId: Long) {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            remoteArticleIdByLocalId.clear()
            remoteDigestArticlesCache.clear()
            lastRemoteArticlesError = null
            try {
                val digest = digestRepository.getDigestById(digestId)
                val articles = digestRepository.getArticlesForDigest(digestId)
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        digest = digest,
                        articles = articles,
                        articleSourceStates = emptyMap()
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
        if (!digest.isComplete) {
            _uiState.update { it.copy(error = "Digest is still being processed") }
            return
        }
        val file = File(digest.epubFilePath)
        if (!file.exists()) {
            val message = if (digest.isFromGhostwriter) {
                "EPUB not downloaded yet. Download it from Digest History first."
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
     * Clear any error message.
     */
    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * Toggle between processed content and raw source HTML for a specific article.
     */
    fun setArticleSourceMode(article: DigestArticle, useSource: Boolean) {
        updateArticleSourceState(article.id) { current ->
            current.copy(isSourceMode = useSource)
        }

        if (useSource) {
            fetchArticleSource(article, force = false)
        }
    }

    /**
     * Retry fetching source HTML for an article.
     */
    fun retryArticleSource(article: DigestArticle) {
        fetchArticleSource(article, force = true)
    }

    private fun fetchArticleSource(article: DigestArticle, force: Boolean) {
        val remoteDigestId = _uiState.value.digest?.remoteId
        if (remoteDigestId.isNullOrBlank()) {
            updateArticleSourceState(article.id) { current ->
                current.copy(
                    isSourceMode = false,
                    isLoading = false,
                    error = "Source mode is only available for Ghostwriter digests"
                )
            }
            return
        }

        val currentState = _uiState.value.articleSourceStates[article.id] ?: ArticleSourceUiState()
        if (!force && (currentState.isLoading || currentState.sourceHtml != null)) {
            return
        }

        updateArticleSourceState(article.id) { current ->
            current.copy(isLoading = true, error = null)
        }

        viewModelScope.launch {
            val remoteArticles = ensureRemoteDigestArticles(remoteDigestId)
            if (remoteArticles == null) {
                updateArticleSourceState(article.id) { current ->
                    current.copy(
                        isLoading = false,
                        error = lastRemoteArticlesError ?: "Failed to load article metadata from server"
                    )
                }
                return@launch
            }

            val remoteArticleId = remoteArticleIdByLocalId[article.id] ?: resolveRemoteArticleId(article, remoteArticles)
            if (remoteArticleId == null) {
                updateArticleSourceState(article.id) { current ->
                    current.copy(
                        isLoading = false,
                        error = "Could not match this article with Ghostwriter source data"
                    )
                }
                return@launch
            }
            remoteArticleIdByLocalId[article.id] = remoteArticleId

            when (val result = ghostwriterRepository.getDigestArticleSource(remoteDigestId, remoteArticleId)) {
                is GhostwriterResult.Success -> {
                    updateArticleSourceState(article.id) { current ->
                        current.copy(
                            isLoading = false,
                            sourceHtml = result.data.html,
                            error = null
                        )
                    }
                }
                is GhostwriterResult.Error -> {
                    updateArticleSourceState(article.id) { current ->
                        current.copy(
                            isLoading = false,
                            error = result.message
                        )
                    }
                }
                is GhostwriterResult.NotConfigured -> {
                    updateArticleSourceState(article.id) { current ->
                        current.copy(
                            isLoading = false,
                            error = "Ghostwriter is not configured"
                        )
                    }
                }
            }
        }
    }

    private suspend fun ensureRemoteDigestArticles(remoteDigestId: String): List<DigestArticleResponse>? {
        remoteDigestArticlesCache[remoteDigestId]?.let {
            return it
        }

        return when (val result = ghostwriterRepository.getDigestArticles(remoteDigestId)) {
            is GhostwriterResult.Success -> {
                lastRemoteArticlesError = null
                result.data.articles.also { remoteDigestArticlesCache[remoteDigestId] = it }
            }
            is GhostwriterResult.Error -> {
                lastRemoteArticlesError = result.message
                null
            }
            is GhostwriterResult.NotConfigured -> {
                lastRemoteArticlesError = "Ghostwriter is not configured"
                null
            }
        }
    }

    private fun resolveRemoteArticleId(
        article: DigestArticle,
        remoteArticles: List<DigestArticleResponse>
    ): String? {
        val normalizedUrl = article.originalUrl.trim()
        val normalizedTitle = article.title.trim()

        remoteArticles.firstOrNull {
            it.url.trim() == normalizedUrl && it.title.trim() == normalizedTitle
        }?.let { return it.id }

        remoteArticles.firstOrNull {
            it.url.trim() == normalizedUrl
        }?.let { return it.id }

        remoteArticles.firstOrNull {
            it.title.trim() == normalizedTitle
        }?.let { return it.id }

        return null
    }

    private fun updateArticleSourceState(
        articleId: Long,
        transform: (ArticleSourceUiState) -> ArticleSourceUiState
    ) {
        _uiState.update { state ->
            val updated = state.articleSourceStates.toMutableMap()
            updated[articleId] = transform(updated[articleId] ?: ArticleSourceUiState())
            state.copy(articleSourceStates = updated)
        }
    }
}

/**
 * UI state for the digest detail screen.
 */
data class DigestDetailUiState(
    val isLoading: Boolean = false,
    val digest: Digest? = null,
    val articles: List<DigestArticle> = emptyList(),
    val articleSourceStates: Map<Long, ArticleSourceUiState> = emptyMap(),
    val error: String? = null
)

/**
 * Source-mode state for an individual digest article card.
 */
data class ArticleSourceUiState(
    val isSourceMode: Boolean = false,
    val isLoading: Boolean = false,
    val sourceHtml: String? = null,
    val error: String? = null
)
