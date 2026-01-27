package com.example.epilogue.ui.feed

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.ui.LocalEinkMode

private const val FEEDS_PER_PAGE = 5

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FeedManagerScreen(
    onNavigateToSettings: () -> Unit = {},
    onNavigateToHistory: () -> Unit = {},
    modifier: Modifier = Modifier,
    viewModel: FeedViewModel = hiltViewModel()
) {
    val feeds by viewModel.feeds.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val einkMode = LocalEinkMode.current

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { Text("Feed Manager") },
                actions = {
                    IconButton(onClick = onNavigateToHistory) {
                        Icon(Icons.Default.History, contentDescription = "History")
                    }
                    IconButton(onClick = onNavigateToSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                }
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = { viewModel.showAddDialog() }) {
                Icon(Icons.Default.Add, contentDescription = "Add Feed")
            }
        }
    ) { innerPadding ->
        if (feeds.isEmpty()) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "No feeds added yet",
                    style = MaterialTheme.typography.bodyLarge
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Tap + to add your first RSS feed",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        } else if (einkMode) {
            // E-ink mode: Paginated feed list
            PaginatedFeedList(
                feeds = feeds,
                onFeedClick = { viewModel.showEditDialog(it) },
                onFeedDelete = { viewModel.deleteFeed(it) },
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = innerPadding.calculateTopPadding())
            )
        } else {
            // Standard mode: Scrollable list
            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(feeds, key = { it.url }) { feed ->
                    FeedItem(
                        feed = feed,
                        onClick = { viewModel.showEditDialog(feed) },
                        onDelete = { viewModel.deleteFeed(feed) }
                    )
                }
            }
        }
    }

    if (uiState.showAddDialog) {
        AddFeedDialog(
            onDismiss = { viewModel.hideAddDialog() },
            onConfirm = { url, name, mode, maxArticles ->
                viewModel.addFeed(url, name, mode, maxArticles)
                viewModel.hideAddDialog()
            }
        )
    }

    uiState.editingFeed?.let { feed ->
        EditFeedDialog(
            feed = feed,
            onDismiss = { viewModel.hideEditDialog() },
            onConfirm = { updatedFeed ->
                viewModel.updateFeed(updatedFeed)
                viewModel.hideEditDialog()
            }
        )
    }
}

/**
 * Paginated feed list for e-ink mode.
 */
@Composable
fun PaginatedFeedList(
    feeds: List<Feed>,
    onFeedClick: (Feed) -> Unit,
    onFeedDelete: (Feed) -> Unit,
    modifier: Modifier = Modifier
) {
    var currentPage by rememberSaveable { mutableIntStateOf(0) }
    val totalPages = (feeds.size + FEEDS_PER_PAGE - 1) / FEEDS_PER_PAGE
    val startIndex = currentPage * FEEDS_PER_PAGE
    val endIndex = minOf(startIndex + FEEDS_PER_PAGE, feeds.size)
    val currentFeeds = feeds.subList(startIndex, endIndex)

    // Reset page if feeds change and current page is out of bounds
    if (currentPage >= totalPages && totalPages > 0) {
        currentPage = totalPages - 1
    }

    Box(modifier = modifier) {
        // Feed items
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .padding(bottom = if (totalPages > 1) 56.dp else 0.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Spacer(modifier = Modifier.height(8.dp))
            currentFeeds.forEach { feed ->
                FeedItem(
                    feed = feed,
                    onClick = { onFeedClick(feed) },
                    onDelete = { onFeedDelete(feed) }
                )
            }
        }

        // Pagination controls (only show if more than one page)
        if (totalPages > 1) {
            val navBarPadding = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .align(Alignment.BottomCenter)
                    .padding(horizontal = 16.dp)
                    .padding(bottom = navBarPadding + 16.dp),  // Account for nav bar + space for FAB
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedButton(
                    onClick = { if (currentPage > 0) currentPage-- },
                    enabled = currentPage > 0,
                    modifier = Modifier.height(48.dp)
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.KeyboardArrowLeft,
                        contentDescription = "Previous"
                    )
                    Text("Prev")
                }

                Text(
                    text = "${currentPage + 1} / $totalPages",
                    style = MaterialTheme.typography.titleMedium,
                    textAlign = TextAlign.Center
                )

                OutlinedButton(
                    onClick = { if (currentPage < totalPages - 1) currentPage++ },
                    enabled = currentPage < totalPages - 1,
                    modifier = Modifier.height(48.dp)
                ) {
                    Text("Next")
                    Icon(
                        imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                        contentDescription = "Next"
                    )
                }
            }
        }
    }
}

@Composable
fun FeedItem(
    feed: Feed,
    onClick: () -> Unit,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier
) {
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
                Text(
                    text = feed.name,
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    text = feed.url,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1
                )
                Spacer(modifier = Modifier.height(4.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = if (feed.mode == ProcessingMode.FIDELITY) "Fidelity" else "Briefing",
                        style = MaterialTheme.typography.labelMedium
                    )
                    if (feed.maxArticles > 0) {
                        Text(
                            text = "Max: ${feed.maxArticles}",
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Delete")
            }
        }
    }
}

private val maxArticleOptions = listOf(5, 10, 15, 20, 25, 30, 50, 0) // 0 = Unlimited

@Composable
fun AddFeedDialog(
    onDismiss: () -> Unit,
    onConfirm: (url: String, name: String, mode: ProcessingMode, maxArticles: Int) -> Unit
) {
    var url by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf(ProcessingMode.FIDELITY) }
    var maxArticlesIndex by remember { mutableStateOf(maxArticleOptions.lastIndex) } // Default to Unlimited
    val maxArticles = maxArticleOptions[maxArticlesIndex]

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Feed") },
        text = {
            Column {
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    label = { Text("Feed URL") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Nickname") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text("Processing Mode", style = MaterialTheme.typography.labelLarge)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = mode == ProcessingMode.FIDELITY,
                        onClick = { mode = ProcessingMode.FIDELITY }
                    )
                    Text("Fidelity")
                    Spacer(modifier = Modifier.width(16.dp))
                    RadioButton(
                        selected = mode == ProcessingMode.BRIEFING,
                        onClick = { mode = ProcessingMode.BRIEFING }
                    )
                    Text("Briefing")
                }
                Spacer(modifier = Modifier.height(16.dp))
                Text("Max articles", style = MaterialTheme.typography.labelLarge)
                Spacer(modifier = Modifier.height(8.dp))
                // Stepper control - easier for e-ink than slider
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedButton(
                        onClick = {
                            if (maxArticlesIndex > 0) maxArticlesIndex--
                        },
                        enabled = maxArticlesIndex > 0
                    ) {
                        Text("-")
                    }

                    Text(
                        text = if (maxArticles == 0) "Unlimited" else "$maxArticles",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.width(80.dp),
                        textAlign = TextAlign.Center
                    )

                    OutlinedButton(
                        onClick = {
                            if (maxArticlesIndex < maxArticleOptions.lastIndex) maxArticlesIndex++
                        },
                        enabled = maxArticlesIndex < maxArticleOptions.lastIndex
                    ) {
                        Text("+")
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(url, name, mode, maxArticles) },
                enabled = url.isNotBlank() && name.isNotBlank()
            ) {
                Text("Add")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

@Composable
fun EditFeedDialog(
    feed: Feed,
    onDismiss: () -> Unit,
    onConfirm: (Feed) -> Unit
) {
    var name by remember { mutableStateOf(feed.name) }
    var mode by remember { mutableStateOf(feed.mode) }
    val initialIndex = maxArticleOptions.indexOf(feed.maxArticles).takeIf { it >= 0 } ?: maxArticleOptions.lastIndex
    var maxArticlesIndex by remember { mutableStateOf(initialIndex) }
    val maxArticles = maxArticleOptions[maxArticlesIndex]

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit Feed") },
        text = {
            Column {
                Text(
                    text = feed.url,
                    style = MaterialTheme.typography.bodySmall
                )
                Spacer(modifier = Modifier.height(16.dp))
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Nickname") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text("Processing Mode", style = MaterialTheme.typography.labelLarge)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(
                        selected = mode == ProcessingMode.FIDELITY,
                        onClick = { mode = ProcessingMode.FIDELITY }
                    )
                    Text("Fidelity")
                    Spacer(modifier = Modifier.width(16.dp))
                    RadioButton(
                        selected = mode == ProcessingMode.BRIEFING,
                        onClick = { mode = ProcessingMode.BRIEFING }
                    )
                    Text("Briefing")
                }
                Spacer(modifier = Modifier.height(16.dp))
                Text("Max articles", style = MaterialTheme.typography.labelLarge)
                Spacer(modifier = Modifier.height(8.dp))
                // Stepper control - easier for e-ink than slider
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedButton(
                        onClick = {
                            if (maxArticlesIndex > 0) maxArticlesIndex--
                        },
                        enabled = maxArticlesIndex > 0
                    ) {
                        Text("-")
                    }

                    Text(
                        text = if (maxArticles == 0) "Unlimited" else "$maxArticles",
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.width(80.dp),
                        textAlign = TextAlign.Center
                    )

                    OutlinedButton(
                        onClick = {
                            if (maxArticlesIndex < maxArticleOptions.lastIndex) maxArticlesIndex++
                        },
                        enabled = maxArticlesIndex < maxArticleOptions.lastIndex
                    ) {
                        Text("+")
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onConfirm(feed.copy(name = name.trim(), mode = mode, maxArticles = maxArticles))
                },
                enabled = name.isNotBlank()
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}
