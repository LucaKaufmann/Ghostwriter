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
import androidx.compose.material3.Switch
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
import com.example.epilogue.data.local.FeedMutationEntity
import com.example.epilogue.ui.LocalEinkMode
import com.example.epilogue.ui.components.SyncStatusIndicator
import com.example.epilogue.service.DigestSyncWorker
import com.example.epilogue.service.FeedSyncWorker
import org.json.JSONObject

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
    val unresolved by viewModel.unresolved.collectAsState()
    val syncState by viewModel.syncState.collectAsState()
    val uiState by viewModel.uiState.collectAsState()
    val einkMode = LocalEinkMode.current

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { Text("Feed Manager") },
                actions = {
                    SyncStatusIndicator(
                        tags = listOf(FeedSyncWorker.TAG, DigestSyncWorker.TAG),
                        modifier = Modifier.padding(end = 8.dp)
                    )
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
        if (feeds.isEmpty() && unresolved.isEmpty() && syncState?.lastOutcome !in setOf("server_changed", "server_upgrade_required", "failed", "partial")) {
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
        } else if (einkMode && unresolved.isEmpty() &&
            syncState?.lastOutcome !in setOf("server_changed", "server_upgrade_required", "failed", "partial") &&
            uiState.error == null && uiState.olderServerPreview.isEmpty()) {
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
                syncState?.takeIf { it.lastOutcome in setOf("server_changed", "server_upgrade_required", "failed", "partial") }?.let { state ->
                    item {
                        Card(Modifier.fillMaxWidth()) {
                            Text(when (state.lastOutcome) {
                                "server_changed" -> "Feed sync paused: server or destination changed. Resolve binding before sending edits."
                                "server_upgrade_required" -> "Feed sync paused: server upgrade required. Local edits are safe on this device."
                                else -> "Feed sync ${state.lastOutcome}: ${state.lastDiagnostic ?: "Review pending edits"}"
                            }, Modifier.padding(16.dp))
                            if (state.lastOutcome == "server_upgrade_required") {
                                TextButton(onClick = viewModel::previewOlderServerFeeds) {
                                    Text("Preview server feeds (read only)")
                                }
                            } else if (state.lastOutcome == "server_changed") {
                                TextButton(onClick = viewModel::reviewChangedServer) {
                                    Text("Review this server's feeds")
                                }
                            }
                        }
                    }
                }
                if (uiState.olderServerPreview.isNotEmpty()) item {
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp)) {
                            Text("Older server feeds — read only", style = MaterialTheme.typography.titleMedium)
                            uiState.olderServerPreview.forEach { Text("${it.title} · ${it.url}") }
                        }
                    }
                }
                uiState.error?.let { message -> item { Text(message, color = MaterialTheme.colorScheme.error) } }
                items(unresolved, key = { "proposal-${it.opId}" }) { proposal ->
                    FeedResolutionCard(proposal,
                        onResolve = { action -> viewModel.resolve(proposal.opId, action) },
                        onCorrect = { title, mode, enabled, cap ->
                            viewModel.correctRejected(proposal.opId, title, mode, enabled, cap)
                        })
                }
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
            error = uiState.error,
            onConfirm = { url, name, mode, maxArticles, isEnabled ->
                viewModel.addFeed(url, name, mode, maxArticles, isEnabled)
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

internal data class FeedCorrectionDraft(
    val title: String,
    val mode: ProcessingMode,
    val enabled: Boolean,
    val maxArticles: Int
)

internal data class FeedCorrectionForm(
    val title: String,
    val cap: String,
    val mode: ProcessingMode,
    val enabled: Boolean
)

/** Only edited fields override the latest rejected-head and server values. */
internal fun correctionForm(draft: FeedCorrectionDraft, titleEdit: String?, capEdit: String?,
    briefingEdit: Boolean?, enabledEdit: Boolean?): FeedCorrectionForm = FeedCorrectionForm(
    titleEdit ?: draft.title,
    capEdit ?: draft.maxArticles.toString(),
    briefingEdit?.let { if (it) ProcessingMode.BRIEFING else ProcessingMode.FIDELITY } ?: draft.mode,
    enabledEdit ?: draft.enabled
)

/** A correction may use the rejected head and its server snapshot, never a later optimistic row. */
internal fun correctionDraft(proposal: FeedMutationEntity): FeedCorrectionDraft? {
    val fields = runCatching { JSONObject(proposal.fieldsJson) }.getOrNull() ?: return null
    val server = proposal.serverSnapshotJson?.let { runCatching { JSONObject(it) }.getOrNull() }
        ?.takeIf { it.optString("kind") == "feed" }
    val title = when {
        fields.has("title") -> fields.optString("title")
        server?.has("title") == true -> server.optString("title")
        else -> return null
    }
    val modeValue = when {
        fields.has("mode") -> fields.optString("mode")
        server?.has("mode") == true -> server.optString("mode")
        else -> return null
    }
    val enabled = when {
        fields.has("is_active") -> fields.optBoolean("is_active")
        server?.has("is_active") == true -> server.optBoolean("is_active")
        else -> return null
    }
    val cap = when {
        fields.has("max_articles") -> fields.optInt("max_articles")
        server?.has("max_articles") == true -> server.optInt("max_articles")
        else -> return null
    }
    if (modeValue !in setOf("raw", "summarize")) return null
    return FeedCorrectionDraft(title, if (modeValue == "summarize") ProcessingMode.BRIEFING else ProcessingMode.FIDELITY,
        enabled, cap)
}

@Composable
private fun FeedResolutionCard(
    proposal: FeedMutationEntity,
    onResolve: (String) -> Unit,
    onCorrect: (String, ProcessingMode, Boolean, Int) -> Unit
) {
    val draft = remember(proposal.opId, proposal.fieldsJson, proposal.serverSnapshotJson) {
        correctionDraft(proposal)
    }
    val local = remember(proposal.fieldsJson) { runCatching { JSONObject(proposal.fieldsJson) }.getOrDefault(JSONObject()) }
    val server = remember(proposal.serverSnapshotJson) {
        proposal.serverSnapshotJson?.let { runCatching { JSONObject(it) }.getOrNull() }
    }
    var correcting by rememberSaveable(proposal.opId) { mutableStateOf(false) }
    val absent = server == null || server.optString("kind") == "tombstone"
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(proposal.url, style = MaterialTheme.typography.titleMedium)
            Text(if (proposal.state == "rejected") "Rejected: ${proposal.rejectionCode ?: "invalid proposal"}"
                else if (absent) "Not present on server" else "Feed conflict",
                color = MaterialTheme.colorScheme.error)
            proposal.rejectionMessage?.let { Text(it) }
            Text("Server: " + if (absent) "removed or absent" else
                "${server!!.optString("title")} · ${feedModeLabel(server.optString("mode"))} · " +
                    "${feedEnabledLabel(server.optBoolean("is_active"))} · ${feedCapLabel(server.optInt("max_articles"))}")
            Text("Your proposal: " + if (proposal.kind == "delete") "Delete feed" else
                "${local.optString("title", "unchanged")} · ${if (local.has("mode")) feedModeLabel(local.optString("mode")) else "unchanged"} · " +
                    "${if (local.has("is_active")) feedEnabledLabel(local.optBoolean("is_active")) else "unchanged"} · " +
                    "${if (local.has("max_articles")) feedCapLabel(local.optInt("max_articles")) else "unchanged"}")
            Text("Later edits for this feed remain blocked until you resolve them.",
                style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                when {
                    proposal.state == "rejected" -> {
                        TextButton(onClick = { onResolve("discard") }) { Text("Discard") }
                        TextButton(onClick = { if (proposal.kind == "delete") onResolve("correct") else correcting = true },
                            enabled = proposal.kind == "delete" || draft != null) {
                            Text("Correct")
                        }
                    }
                    proposal.kind == "delete" -> {
                        TextButton(onClick = { onResolve("keep_feed") }) { Text("Keep feed") }
                        TextButton(onClick = { onResolve("delete_anyway") }) { Text("Delete anyway") }
                    }
                    absent -> {
                        TextButton(onClick = { onResolve("keep_removed") }) { Text("Keep removed") }
                        TextButton(onClick = { onResolve("add_to_server") }) { Text("Add to server") }
                    }
                    else -> {
                        TextButton(onClick = { onResolve("keep_server") }) { Text("Keep server") }
                        TextButton(onClick = { onResolve("apply_mine") }) { Text("Apply mine") }
                    }
                }
            }
            if (proposal.state == "rejected" && proposal.kind != "delete" && draft == null) {
                Text("This proposal lacks the server values needed for a safe correction. Discard it and edit the feed again.",
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
    if (correcting && draft != null) {
        var titleEdit by rememberSaveable(proposal.opId) {
            mutableStateOf<String?>(null)
        }
        var capEdit by rememberSaveable(proposal.opId) {
            mutableStateOf<String?>(null)
        }
        var briefingEdit by rememberSaveable(proposal.opId) {
            mutableStateOf<Boolean?>(null)
        }
        var enabledEdit by rememberSaveable(proposal.opId) {
            mutableStateOf<Boolean?>(null)
        }
        val form = correctionForm(draft, titleEdit, capEdit, briefingEdit, enabledEdit)
        AlertDialog(
            onDismissRequest = { correcting = false },
            title = { Text("Correct feed proposal") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(form.title, { titleEdit = it }, label = { Text("Title") })
                    OutlinedTextField(form.cap, { capEdit = it }, label = { Text("Max articles (0 = unlimited)") })
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Summarize")
                        Switch(checked = form.mode == ProcessingMode.BRIEFING,
                            onCheckedChange = { briefingEdit = it })
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Enabled")
                        Switch(checked = form.enabled, onCheckedChange = { enabledEdit = it })
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val number = form.cap.toIntOrNull()
                    if (form.title.isNotBlank() && number != null && number >= 0) {
                        onCorrect(form.title, form.mode, form.enabled, number)
                        correcting = false
                    }
                }) { Text("Save correction") }
            },
            dismissButton = { TextButton(onClick = { correcting = false }) { Text("Cancel") } }
        )
    }
}

private fun feedModeLabel(mode: String): String = when (mode) {
    "raw" -> "Fidelity"
    "summarize" -> "Briefing"
    else -> mode
}

private fun feedEnabledLabel(enabled: Boolean): String = if (enabled) "Enabled" else "Paused"

private fun feedCapLabel(cap: Int): String = if (cap == 0) "Unlimited" else "Max $cap articles"

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
                    if (!feed.isEnabled) {
                        Text(
                            text = "Paused",
                            style = MaterialTheme.typography.labelMedium
                        )
                    }
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

private val maxArticleOptions = listOf(5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 0) // 0 = Unlimited

@Composable
fun AddFeedDialog(
    onDismiss: () -> Unit,
    error: String? = null,
    onConfirm: (
        url: String,
        name: String,
        mode: ProcessingMode,
        maxArticles: Int,
        isEnabled: Boolean
    ) -> Unit
) {
    var url by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var mode by remember { mutableStateOf(ProcessingMode.FIDELITY) }
    var isEnabled by remember { mutableStateOf(true) }
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
                    singleLine = true,
                    isError = error != null
                )
                if (error != null) {
                    Text(error, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
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
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Enabled", style = MaterialTheme.typography.labelLarge)
                    Switch(
                        checked = isEnabled,
                        onCheckedChange = { isEnabled = it }
                    )
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
                onClick = { onConfirm(url, name, mode, maxArticles, isEnabled) },
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
    var isEnabled by remember { mutableStateOf(feed.isEnabled) }
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
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Enabled", style = MaterialTheme.typography.labelLarge)
                    Switch(
                        checked = isEnabled,
                        onCheckedChange = { isEnabled = it }
                    )
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
                    onConfirm(
                        feed.copy(
                            name = name.trim(),
                            mode = mode,
                            maxArticles = maxArticles,
                            isEnabled = isEnabled
                        )
                    )
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
