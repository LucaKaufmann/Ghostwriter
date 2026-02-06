package com.example.epilogue.ui.history

import android.graphics.Typeface
import android.text.method.LinkMovementMethod
import android.util.TypedValue
import android.widget.TextView
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.text.HtmlCompat
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.DigestArticle
import com.example.epilogue.ui.LocalEinkMode
import com.example.epilogue.ui.components.EinkBookReader
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Screen displaying the full content of a digest.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DigestDetailScreen(
    digestId: Long,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: DigestDetailViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val dateFormat = remember { SimpleDateFormat("MMM d, yyyy", Locale.getDefault()) }

    // E-ink mode support
    val einkMode = LocalEinkMode.current

    // Load digest when screen appears
    LaunchedEffect(digestId) {
        viewModel.loadDigest(digestId)
    }

    // Show error in snackbar
    LaunchedEffect(uiState.error) {
        uiState.error?.let { error ->
            snackbarHostState.showSnackbar(error)
            viewModel.clearError()
        }
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        uiState.digest?.let {
                            dateFormat.format(Date(it.generatedAt))
                        } ?: "Digest"
                    )
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    uiState.digest?.let {
                        IconButton(onClick = { viewModel.openInExternalReader() }) {
                            Icon(
                                imageVector = Icons.Default.OpenInNew,
                                contentDescription = "Open in reader"
                            )
                        }
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { innerPadding ->
        when {
            uiState.isLoading -> {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(innerPadding),
                    contentAlignment = Alignment.Center
                ) {
                    Text("Loading...")
                }
            }
            uiState.digest == null -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(innerPadding)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "Digest not found",
                        style = MaterialTheme.typography.titleLarge
                    )
                }
            }
            else -> {
                val digest = uiState.digest!!
                val isRemoteDigest = digest.remoteId != null
                val orderedArticles = uiState.articles

                // For remote digests (synced from Ghostwriter), show prompt to open EPUB
                // since we don't have individual article records
                if (isRemoteDigest && uiState.articles.isEmpty()) {
                    RemoteDigestContent(
                        digest = digest,
                        onOpenInReader = { viewModel.openInExternalReader() },
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(innerPadding)
                    )
                } else if (einkMode) {
                    // E-ink mode: Book-style reader with all articles as chapters
                    // Only apply top padding (for app bar), ignore bottom system padding
                    EinkBookReader(
                        articles = orderedArticles,
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(top = innerPadding.calculateTopPadding())
                    )
                } else {
                    // Standard mode: Scrollable list
                    ScrollableArticleList(
                        articles = orderedArticles,
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(innerPadding)
                            .padding(horizontal = 16.dp)
                    )
                }
            }
        }
    }
}

/**
 * Standard scrollable article list (non-e-ink mode).
 */
@Composable
fun ScrollableArticleList(
    articles: List<DigestArticle>,
    modifier: Modifier = Modifier
) {
    val einkMode = LocalEinkMode.current
    val groupedArticles = remember(articles) {
        val grouped = linkedMapOf<String, MutableList<DigestArticle>>()
        for (article in articles) {
            val feed = article.feedName.ifBlank { "Unknown Feed" }
            grouped.getOrPut(feed) { mutableListOf() }.add(article)
        }
        grouped.toList()
    }

    LazyColumn(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item { Spacer(modifier = Modifier.height(8.dp)) }

        if (groupedArticles.isEmpty()) {
            item {
                Text(
                    text = "No articles in this digest",
                    style = MaterialTheme.typography.bodyLarge
                )
            }
        } else {
            groupedArticles.forEach { (feedName, feedArticles) ->
                item {
                    Column {
                        Text(
                            text = feedName,
                            style = MaterialTheme.typography.headlineSmall
                        )
                        Text(
                            text = "${feedArticles.size} article${if (feedArticles.size == 1) "" else "s"}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                items(feedArticles, key = { it.id }) { article ->
                    ArticleCard(article = article, einkMode = einkMode)
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

/**
 * Card displaying a single article with expandable content.
 */
@Composable
fun ArticleCard(
    article: DigestArticle,
    modifier: Modifier = Modifier,
    einkMode: Boolean = false
) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val textColor = MaterialTheme.colorScheme.onSurface.toArgb()
    val linkColor = MaterialTheme.colorScheme.primary.toArgb()

    Card(
        modifier = modifier
            .fillMaxWidth()
            .then(if (einkMode) Modifier else Modifier.animateContentSize())
            .clickable { expanded = !expanded },
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        ),
        border = CardDefaults.outlinedCardBorder()
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Title
            Text(
                text = article.title,
                style = MaterialTheme.typography.titleMedium
            )

            // Author
            if (article.author.isNotBlank()) {
                Text(
                    text = "By ${article.author}",
                    style = MaterialTheme.typography.bodySmall,
                    fontStyle = FontStyle.Italic,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Feed name
            Text(
                text = "From: ${article.feedName}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Spacer(modifier = Modifier.height(8.dp))

            if (expanded) {
                // Full content - use AndroidView with TextView for proper HTML rendering
                val htmlContent = remember(article.content) {
                    HtmlCompat.fromHtml(article.content, HtmlCompat.FROM_HTML_MODE_LEGACY)
                }

                AndroidView(
                    factory = { context ->
                        TextView(context).apply {
                            // Text styling
                            setTextColor(textColor)
                            setLinkTextColor(linkColor)
                            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                            setLineSpacing(4f, 1.2f)
                            typeface = Typeface.create("sans-serif", Typeface.NORMAL)

                            // Enable clickable links
                            movementMethod = LinkMovementMethod.getInstance()

                            // Remove extra padding that TextView adds
                            includeFontPadding = false
                        }
                    },
                    update = { textView ->
                        textView.text = htmlContent
                        textView.setTextColor(textColor)
                        textView.setLinkTextColor(linkColor)
                    },
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Tap to collapse",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.outline
                )
            } else {
                // Preview - first 200 characters of plain text
                val preview = remember(article.content) {
                    val plainText = HtmlCompat.fromHtml(article.content, HtmlCompat.FROM_HTML_MODE_COMPACT)
                        .toString()
                        .trim()
                    if (plainText.length > 200) {
                        plainText.take(200) + "..."
                    } else {
                        plainText
                    }
                }
                Text(
                    text = preview,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Tap to expand",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.outline
                )
            }
        }
    }
}

/**
 * Content displayed for digests synced from Ghostwriter.
 * Since we don't have individual article records, prompts user to open the EPUB.
 */
@Composable
fun RemoteDigestContent(
    digest: Digest,
    onOpenInReader: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            imageVector = Icons.Default.OpenInNew,
            contentDescription = null,
            modifier = Modifier.padding(bottom = 16.dp),
            tint = MaterialTheme.colorScheme.primary
        )

        Text(
            text = "Synced from Ghostwriter",
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "This digest contains ${digest.articleCount} articles.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        Button(
            onClick = onOpenInReader,
            colors = ButtonDefaults.buttonColors(
                containerColor = MaterialTheme.colorScheme.primary
            )
        ) {
            Icon(
                imageVector = Icons.Default.OpenInNew,
                contentDescription = null,
                modifier = Modifier.padding(end = 8.dp)
            )
            Text("Open in Reader")
        }

        Text(
            text = "The EPUB file will open in your preferred reader app.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
            modifier = Modifier.padding(top = 16.dp)
        )
    }
}
