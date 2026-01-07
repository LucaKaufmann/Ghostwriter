package com.example.epilog.ui.feed

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.epilog.domain.model.Feed
import com.example.epilog.domain.model.ProcessingMode

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
        } else {
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
            onConfirm = { url, name, mode ->
                viewModel.addFeed(url, name, mode)
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
                Text(
                    text = if (feed.mode == ProcessingMode.FIDELITY) "Fidelity" else "Briefing",
                    style = MaterialTheme.typography.labelMedium
                )
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, contentDescription = "Delete")
            }
        }
    }
}

@Composable
fun AddFeedDialog(
    onDismiss: () -> Unit,
    onConfirm: (url: String, name: String, mode: ProcessingMode) -> Unit
) {
    var url by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf(ProcessingMode.FIDELITY) }

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
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(url, name, mode) },
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
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onConfirm(feed.copy(name = name.trim(), mode = mode))
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
