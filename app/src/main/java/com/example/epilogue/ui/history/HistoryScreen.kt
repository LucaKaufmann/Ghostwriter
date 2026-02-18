package com.example.epilogue.ui.history

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
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
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.epilogue.domain.model.Digest
import com.example.epilogue.domain.model.TriggerType
import com.example.epilogue.service.DigestSyncWorker
import com.example.epilogue.ui.components.SyncStatusIndicator
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Screen displaying the history of generated digests.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    onNavigateBack: () -> Unit,
    onDigestClick: (Long) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: HistoryViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val digests by viewModel.digests.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    // Show error in snackbar
    LaunchedEffect(uiState.error) {
        uiState.error?.let { error ->
            snackbarHostState.showSnackbar(error)
            viewModel.clearError()
        }
    }

    val pullToRefreshState = rememberPullToRefreshState()

    // Handle pull-to-refresh
    LaunchedEffect(pullToRefreshState.isRefreshing) {
        if (pullToRefreshState.isRefreshing) {
            viewModel.refresh()
        }
    }

    // End refreshing when ViewModel finishes
    LaunchedEffect(uiState.isRefreshing) {
        if (!uiState.isRefreshing) {
            pullToRefreshState.endRefresh()
        }
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { Text("Digest History") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    SyncStatusIndicator(
                        tags = listOf(DigestSyncWorker.TAG),
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    IconButton(
                        onClick = { viewModel.refresh() },
                        enabled = !uiState.isRefreshing
                    ) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = innerPadding.calculateTopPadding())
                .nestedScroll(pullToRefreshState.nestedScrollConnection)
        ) {
            if (digests.isEmpty()) {
                // Empty state
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = "No digests yet",
                        style = MaterialTheme.typography.titleLarge
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Generate your first digest from Settings",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(
                        start = 16.dp,
                        end = 16.dp,
                        top = 8.dp,
                        bottom = 16.dp
                    ),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(digests, key = { it.id }) { digest ->
                        DigestHistoryItem(
                            digest = digest,
                            onClick = { onDigestClick(digest.id) },
                            onDelete = { viewModel.showDeleteConfirmation(digest) },
                            onOpenExternal = { viewModel.openInExternalReader(digest) },
                            onDownload = { viewModel.downloadEpub(digest) },
                            onDownloadPdf = { viewModel.downloadPdf(digest) },
                            isDownloading = uiState.downloadingDigestIds.contains(digest.id)
                        )
                    }
                }
            }

            PullToRefreshContainer(
                state = pullToRefreshState,
                modifier = Modifier.align(Alignment.TopCenter)
            )
        }
    }

    // Delete confirmation dialog
    uiState.digestToDelete?.let { digest ->
        AlertDialog(
            onDismissRequest = { viewModel.dismissDeleteConfirmation() },
            title = { Text("Delete Digest?") },
            text = {
                Text("This will permanently delete this digest and its EPUB file.")
            },
            confirmButton = {
                TextButton(onClick = { viewModel.confirmDelete() }) {
                    Text("Delete")
                }
            },
            dismissButton = {
                TextButton(onClick = { viewModel.dismissDeleteConfirmation() }) {
                    Text("Cancel")
                }
            }
        )
    }
}

/**
 * Individual digest item in the history list.
 */
@Composable
fun DigestHistoryItem(
    digest: Digest,
    onClick: () -> Unit,
    onDelete: () -> Unit,
    onOpenExternal: () -> Unit,
    onDownload: () -> Unit,
    onDownloadPdf: () -> Unit,
    isDownloading: Boolean,
    modifier: Modifier = Modifier
) {
    val dateFormat = remember { SimpleDateFormat("MMM d, yyyy", Locale.getDefault()) }
    val timeFormat = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }
    val epubExists = remember(digest.epubFilePath, isDownloading) {
        digest.epubFilePath.isNotBlank() && File(digest.epubFilePath).exists()
    }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        ),
        border = CardDefaults.outlinedCardBorder()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                // Date and period
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = dateFormat.format(Date(digest.generatedAt)),
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text(
                        text = digest.periodDisplay,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                }

                // Time and source
                Text(
                    text = buildString {
                        append(timeFormat.format(Date(digest.generatedAt)))
                        if (digest.isFromGhostwriter) {
                            append(" · Ghostwriter")
                        }
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(4.dp))

                // Article counts
                Text(
                    text = "${digest.articleCount} articles (${digest.briefingCount} briefings, ${digest.fidelityCount} full)",
                    style = MaterialTheme.typography.bodySmall
                )

                // Feed names
                if (digest.feedNames.isNotEmpty()) {
                    val feedText = if (digest.feedNames.size <= 3) {
                        digest.feedNames.joinToString(", ")
                    } else {
                        digest.feedNames.take(3).joinToString(", ") +
                                " +${digest.feedNames.size - 3} more"
                    }
                    Text(
                        text = feedText,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1
                    )
                }

                if (digest.isFromGhostwriter && !epubExists) {
                    Text(
                        text = "EPUB not downloaded",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.tertiary
                    )
                }
            }

            // Action buttons
            Row {
                if (digest.isFromGhostwriter) {
                    TextButton(
                        onClick = onDownloadPdf,
                        enabled = !isDownloading
                    ) {
                        Text(if (isDownloading) "Downloading..." else "PDF")
                    }
                }
                if (digest.isFromGhostwriter && !epubExists) {
                    TextButton(
                        onClick = onDownload,
                        enabled = !isDownloading
                    ) {
                        Text(if (isDownloading) "Downloading..." else "Download")
                    }
                } else {
                    IconButton(onClick = onOpenExternal) {
                        Icon(
                            imageVector = Icons.Default.OpenInNew,
                            contentDescription = "Open in reader"
                        )
                    }
                }
                IconButton(onClick = onDelete) {
                    Icon(
                        imageVector = Icons.Default.Delete,
                        contentDescription = "Delete"
                    )
                }
            }
        }
    }
}
