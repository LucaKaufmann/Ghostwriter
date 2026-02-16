package com.example.epilogue.ui.settings

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Cloud
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import com.example.epilogue.domain.model.DigestPeriod
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.epilogue.data.remote.ghostwriter.DigestStatusResponse
import com.example.epilogue.data.remote.ghostwriter.HealthResponse
import com.example.epilogue.data.remote.ghostwriter.IntegrationStatus
import com.example.epilogue.data.remote.ghostwriter.MediaProcessingStatusResponse

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current

    // SAF directory picker launcher
    val directoryPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        uri?.let {
            // Take persistable permission
            val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            context.contentResolver.takePersistableUriPermission(it, flags)
            viewModel.setCustomExportUri(it)
        }
    }

    LaunchedEffect(uiState.apiKeySaved) {
        if (uiState.apiKeySaved) {
            snackbarHostState.showSnackbar("API key saved")
            viewModel.clearApiKeySavedFlag()
        }
    }

    LaunchedEffect(uiState.digestTriggered) {
        if (uiState.digestTriggered) {
            snackbarHostState.showSnackbar("Digest generation started")
            viewModel.clearDigestTriggeredFlag()
        }
    }

    LaunchedEffect(uiState.digestCompleted) {
        if (uiState.digestCompleted) {
            snackbarHostState.showSnackbar("Digest generated successfully")
            viewModel.clearDigestCompletedFlag()
        }
    }

    LaunchedEffect(uiState.digestFailed) {
        if (uiState.digestFailed) {
            snackbarHostState.showSnackbar("Digest generation failed")
            viewModel.clearDigestFailedFlag()
        }
    }

    LaunchedEffect(uiState.dataReset) {
        if (uiState.dataReset) {
            snackbarHostState.showSnackbar("All digests deleted and feed timestamps reset")
            viewModel.clearDataResetFlag()
        }
    }

    LaunchedEffect(uiState.ghostwriterUrlSaved) {
        if (uiState.ghostwriterUrlSaved) {
            snackbarHostState.showSnackbar("Server URL saved")
            viewModel.clearGhostwriterUrlSavedFlag()
        }
    }

    LaunchedEffect(uiState.ghostwriterApiKeySaved) {
        if (uiState.ghostwriterApiKeySaved) {
            snackbarHostState.showSnackbar("API key saved")
            viewModel.clearGhostwriterApiKeySavedFlag()
        }
    }

    LaunchedEffect(uiState.ghostwriterTestResult) {
        uiState.ghostwriterTestResult?.let { result ->
            snackbarHostState.showSnackbar(result)
            viewModel.clearGhostwriterTestResult()
        }
    }

    LaunchedEffect(uiState.integrationActionResult) {
        uiState.integrationActionResult?.let { result ->
            snackbarHostState.showSnackbar(result)
            viewModel.clearIntegrationActionResult()
        }
    }

    Scaffold(
        modifier = modifier,
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = innerPadding.calculateTopPadding())
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // API Key Section
            SettingsSection(title = "OpenAI API Key") {
                ApiKeyInput(
                    apiKey = uiState.apiKey,
                    onApiKeyChange = viewModel::updateApiKey,
                    onSave = viewModel::saveApiKey
                )
            }

            Divider()

            // Schedule Section
            SettingsSection(title = "Daily Schedule") {
                PeriodSelection(
                    selectedPeriods = uiState.selectedPeriods,
                    onTogglePeriod = viewModel::togglePeriod
                )
            }

            Divider()

            // Content Settings Section
            SettingsSection(title = "Content Settings") {
                MinWordCountInput(
                    minWordCount = uiState.minWordCount,
                    onMinWordCountChange = viewModel::updateMinWordCount
                )
            }

            Divider()

            // E-ink Mode Section
            SettingsSection(title = "E-ink Mode") {
                EinkModeInput(
                    enabled = uiState.einkMode,
                    onEnabledChange = viewModel::updateEinkMode
                )
            }

            Divider()

            // Export Directory Section
            SettingsSection(title = "Export Directory") {
                CustomExportInput(
                    enabled = uiState.customExportEnabled,
                    displayPath = uiState.customExportDisplayPath,
                    onToggle = viewModel::toggleCustomExport,
                    onSelectDirectory = { directoryPickerLauncher.launch(null) },
                    onClearDirectory = viewModel::clearCustomExportDirectory
                )
            }

            Divider()

            // Ghostwriter Backend Section
            SettingsSection(title = "Ghostwriter Backend") {
                GhostwriterInput(
                    enabled = uiState.ghostwriterEnabled,
                    downloadEpubsOnSync = uiState.ghostwriterDownloadEpubsOnSync,
                    url = uiState.ghostwriterUrl,
                    apiKey = uiState.ghostwriterApiKey,
                    isTesting = uiState.ghostwriterTesting,
                    integrationActionRunning = uiState.integrationActionRunning,
                    mediaRefreshing = uiState.mediaRefreshing,
                    mediaTriggering = uiState.mediaTriggering,
                    podcastFeedCount = uiState.podcastFeedCount,
                    youtubeFeedCount = uiState.youtubeFeedCount,
                    mediaStatus = uiState.mediaStatus,
                    recentMediaItems = uiState.recentMediaItems,
                    health = uiState.ghostwriterHealth,
                    wallabagIntegration = uiState.wallabagIntegration,
                    newslettersIntegration = uiState.newslettersIntegration,
                    onEnabledChange = viewModel::updateGhostwriterEnabled,
                    onUrlChange = viewModel::updateGhostwriterUrl,
                    onSaveUrl = viewModel::saveGhostwriterUrl,
                    onApiKeyChange = viewModel::updateGhostwriterApiKey,
                    onSaveApiKey = viewModel::saveGhostwriterApiKey,
                    onDownloadEpubsOnSyncChange = viewModel::updateGhostwriterDownloadEpubsOnSync,
                    onTestConnection = viewModel::testGhostwriterConnection,
                    onPreviewWallabag = viewModel::previewWallabag,
                    onPreviewNewsletters = viewModel::previewNewsletters,
                    onClearWallabagSeen = viewModel::clearWallabagSeen,
                    onClearNewslettersSeen = viewModel::clearNewslettersSeen,
                    onRefreshMediaStatus = viewModel::refreshMediaOverview,
                    onTriggerMediaProcessing = viewModel::triggerMediaProcessing,
                    onStartNewsletterOAuth = {
                        val base = uiState.ghostwriterUrl.trim()
                        if (base.isNotBlank()) {
                            val withoutSlash = base.trimEnd('/')
                            val apiBase = if (withoutSlash.endsWith("/api")) {
                                withoutSlash
                            } else {
                                "$withoutSlash/api"
                            }
                            val oauthUrl = "$apiBase/newsletters/oauth/start"
                            runCatching {
                                context.startActivity(
                                    Intent(Intent.ACTION_VIEW, Uri.parse(oauthUrl))
                                )
                            }
                        }
                    }
                )
            }

            Divider()

            // Manual Run Section
            SettingsSection(title = "Manual Generation") {
                ManualGenerationInput(
                    isGenerating = uiState.isGenerating,
                    ghostwriterEnabled = uiState.ghostwriterEnabled && uiState.ghostwriterUrl.isNotBlank(),
                    progress = uiState.ghostwriterProgress,
                    error = uiState.ghostwriterError,
                    onRunNow = viewModel::runDigestNow
                )
            }

            Divider()

            // Developer Section
            SettingsSection(title = "Developer") {
                var showConfirmDialog by remember { mutableStateOf(false) }

                OutlinedButton(
                    onClick = { showConfirmDialog = true },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Reset All Data")
                }
                Text(
                    text = "Deletes all digests and resets feed timestamps (for testing)",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp)
                )

                if (showConfirmDialog) {
                    AlertDialog(
                        onDismissRequest = { showConfirmDialog = false },
                        title = { Text("Reset All Data?") },
                        text = { Text("This will delete all digests and reset feed timestamps so all articles will be fetched again. This cannot be undone.") },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    viewModel.resetAllData()
                                    showConfirmDialog = false
                                }
                            ) {
                                Text("Reset")
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = { showConfirmDialog = false }) {
                                Text("Cancel")
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
fun SettingsSection(
    title: String,
    content: @Composable () -> Unit
) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface
            ),
            border = CardDefaults.outlinedCardBorder()
        ) {
            Column(
                modifier = Modifier.padding(16.dp)
            ) {
                content()
            }
        }
    }
}

@Composable
fun ApiKeyInput(
    apiKey: String,
    onApiKeyChange: (String) -> Unit,
    onSave: () -> Unit
) {
    var showApiKey by remember { mutableStateOf(false) }

    Column {
        OutlinedTextField(
            value = apiKey,
            onValueChange = onApiKeyChange,
            label = { Text("API Key") },
            placeholder = { Text("sk-...") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = if (showApiKey) {
                VisualTransformation.None
            } else {
                PasswordVisualTransformation()
            },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            trailingIcon = {
                IconButton(onClick = { showApiKey = !showApiKey }) {
                    Icon(
                        imageVector = if (showApiKey) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                        contentDescription = if (showApiKey) "Hide" else "Show"
                    )
                }
            }
        )

        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End
        ) {
            Button(onClick = onSave) {
                Text("Save")
            }
        }

        Text(
            text = "Required for Briefing mode. Get your key at platform.openai.com",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 8.dp)
        )
    }
}

@Composable
fun PeriodSelection(
    selectedPeriods: Set<DigestPeriod>,
    onTogglePeriod: (DigestPeriod, Boolean) -> Unit
) {
    Column {
        Text(
            text = "Generate digests at:",
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier.padding(bottom = 12.dp)
        )

        DigestPeriod.entries.forEach { period ->
            val isSelected = period in selectedPeriods
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${period.name.lowercase().replaceFirstChar { it.uppercase() }} - ${period.displayTime}",
                    style = MaterialTheme.typography.bodyLarge
                )
                Switch(
                    checked = isSelected,
                    onCheckedChange = { enabled ->
                        onTogglePeriod(period, enabled)
                    }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = if (selectedPeriods.isEmpty()) {
                "Select at least one time period"
            } else {
                "EPUB will be generated at selected times"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (selectedPeriods.isEmpty()) {
                MaterialTheme.colorScheme.error
            } else {
                MaterialTheme.colorScheme.onSurface
            }
        )
    }
}

@Composable
fun MinWordCountInput(
    minWordCount: Int,
    onMinWordCountChange: (Int) -> Unit
) {
    Column {
        Text(
            text = "Minimum word count",
            style = MaterialTheme.typography.bodyLarge
        )

        Spacer(modifier = Modifier.height(8.dp))

        // Stepper control - easier for e-ink than slider
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedButton(
                onClick = {
                    val newValue = (minWordCount - 100).coerceAtLeast(0)
                    onMinWordCountChange(newValue)
                },
                enabled = minWordCount > 0,
                modifier = Modifier.height(48.dp)
            ) {
                Text("-", style = MaterialTheme.typography.titleLarge)
            }

            Spacer(modifier = Modifier.width(16.dp))

            Text(
                text = if (minWordCount == 0) "Off" else "$minWordCount",
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.width(100.dp),
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.width(16.dp))

            OutlinedButton(
                onClick = {
                    val newValue = (minWordCount + 100).coerceAtMost(1000)
                    onMinWordCountChange(newValue)
                },
                enabled = minWordCount < 1000,
                modifier = Modifier.height(48.dp)
            ) {
                Text("+", style = MaterialTheme.typography.titleLarge)
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "Skip articles shorter than this (0 = include all)",
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth()
        )
    }
}

@Composable
fun EinkModeInput(
    enabled: Boolean,
    onEnabledChange: (Boolean) -> Unit
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Enable E-ink optimizations",
                    style = MaterialTheme.typography.bodyLarge
                )
            }
            Switch(
                checked = enabled,
                onCheckedChange = onEnabledChange
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "Optimizes for e-ink displays: page-based navigation, volume button support, larger touch targets, no animations",
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
fun CustomExportInput(
    enabled: Boolean,
    displayPath: String?,
    onToggle: (Boolean) -> Unit,
    onSelectDirectory: () -> Unit,
    onClearDirectory: () -> Unit
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Export to custom folder",
                    style = MaterialTheme.typography.bodyLarge
                )
                if (displayPath != null) {
                    Text(
                        text = displayPath,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
            Switch(
                checked = enabled && displayPath != null,
                onCheckedChange = onToggle,
                enabled = displayPath != null
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedButton(
                onClick = onSelectDirectory,
                modifier = Modifier.weight(1f)
            ) {
                Text(if (displayPath == null) "Select Folder" else "Change")
            }

            if (displayPath != null) {
                OutlinedButton(
                    onClick = onClearDirectory,
                ) {
                    Text("Clear")
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        Text(
            text = "EPUBs will be automatically copied to this folder (e.g., KOReader)",
            style = MaterialTheme.typography.bodySmall
        )
    }
}

@Composable
fun GhostwriterInput(
    enabled: Boolean,
    downloadEpubsOnSync: Boolean,
    url: String,
    apiKey: String,
    isTesting: Boolean,
    integrationActionRunning: Boolean,
    mediaRefreshing: Boolean,
    mediaTriggering: Boolean,
    podcastFeedCount: Int,
    youtubeFeedCount: Int,
    mediaStatus: MediaProcessingStatusResponse?,
    recentMediaItems: List<MediaItemUi>,
    health: HealthResponse?,
    wallabagIntegration: IntegrationStatus?,
    newslettersIntegration: IntegrationStatus?,
    onEnabledChange: (Boolean) -> Unit,
    onUrlChange: (String) -> Unit,
    onSaveUrl: () -> Unit,
    onApiKeyChange: (String) -> Unit,
    onSaveApiKey: () -> Unit,
    onDownloadEpubsOnSyncChange: (Boolean) -> Unit,
    onTestConnection: () -> Unit,
    onPreviewWallabag: () -> Unit,
    onPreviewNewsletters: () -> Unit,
    onClearWallabagSeen: () -> Unit,
    onClearNewslettersSeen: () -> Unit,
    onRefreshMediaStatus: () -> Unit,
    onTriggerMediaProcessing: () -> Unit,
    onStartNewsletterOAuth: () -> Unit
) {
    var showApiKey by remember { mutableStateOf(false) }

    Column {
        // Enable toggle
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "Use Ghostwriter server",
                    style = MaterialTheme.typography.bodyLarge
                )
                Text(
                    text = "Offload digest generation to a backend server",
                    style = MaterialTheme.typography.bodySmall
                )
            }
            Switch(
                checked = enabled,
                onCheckedChange = onEnabledChange
            )
        }

        // Configuration fields (shown when enabled)
        AnimatedVisibility(visible = enabled) {
            Column {
                Spacer(modifier = Modifier.height(16.dp))

                // Server URL
                OutlinedTextField(
                    value = url,
                    onValueChange = onUrlChange,
                    label = { Text("Server URL") },
                    placeholder = { Text("http://192.168.1.100:8080") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    leadingIcon = {
                        Icon(Icons.Filled.Cloud, contentDescription = null)
                    }
                )

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onSaveUrl,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Save URL")
                    }

                    Button(
                        onClick = onTestConnection,
                        enabled = url.isNotBlank() && !isTesting,
                        modifier = Modifier.weight(1f)
                    ) {
                        if (isTesting) {
                            CircularProgressIndicator(
                                modifier = Modifier.height(16.dp).width(16.dp),
                                strokeWidth = 2.dp
                            )
                        } else {
                            Text("Test")
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // API Token (optional)
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = onApiKeyChange,
                    label = { Text("API Token (optional)") },
                    placeholder = { Text("gw_... or JWT (leave blank if not required)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    visualTransformation = if (showApiKey) {
                        VisualTransformation.None
                    } else {
                        PasswordVisualTransformation()
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    trailingIcon = {
                        IconButton(onClick = { showApiKey = !showApiKey }) {
                            Icon(
                                imageVector = if (showApiKey) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                contentDescription = if (showApiKey) "Hide" else "Show"
                            )
                        }
                    }
                )

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "Use a Ghostwriter API token (gw_...) or a JWT from the web UI.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    Button(onClick = onSaveApiKey) {
                        Text("Save Key")
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "Run Ghostwriter on your home server or NAS. Supports local AI (Ollama) or cloud providers.",
                    style = MaterialTheme.typography.bodySmall
                )

                Spacer(modifier = Modifier.height(16.dp))
                Divider()
                Spacer(modifier = Modifier.height(12.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Download EPUBs on sync",
                            style = MaterialTheme.typography.bodyLarge
                        )
                        Text(
                            text = "When off, digest entries sync first and EPUB files can be downloaded manually from History.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Switch(
                        checked = downloadEpubsOnSync,
                        onCheckedChange = onDownloadEpubsOnSyncChange
                    )
                }

                // Server health summary (shown after successful test)
                if (health != null) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Divider()
                    Spacer(modifier = Modifier.height(8.dp))

                    Text(
                        text = "Server",
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )

                    Text(
                        text = "Version: ${health.version}",
                        style = MaterialTheme.typography.bodySmall
                    )
                    Text(
                        text = "AI: ${health.aiProvider} · ${health.aiModel}",
                        style = MaterialTheme.typography.bodySmall
                    )
                    health.uptimeSeconds?.let { seconds ->
                        Text(
                            text = "Uptime: ${formatUptime(seconds)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }

                // Integration status (shown when connected)
                if (wallabagIntegration != null || newslettersIntegration != null) {
                    Spacer(modifier = Modifier.height(16.dp))
                    Divider()
                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        text = "Integrations",
                        style = MaterialTheme.typography.titleSmall,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )

                    if (wallabagIntegration != null) {
                        IntegrationStatusRow(
                            name = "Wallabag",
                            enabled = wallabagIntegration.enabled
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedButton(
                                onClick = onPreviewWallabag,
                                enabled = !integrationActionRunning,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Preview")
                            }
                            OutlinedButton(
                                onClick = onClearWallabagSeen,
                                enabled = !integrationActionRunning,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Clear Seen")
                            }
                        }
                    }

                    if (newslettersIntegration != null) {
                        Spacer(modifier = Modifier.height(12.dp))
                        IntegrationStatusRow(
                            name = "Newsletters",
                            enabled = newslettersIntegration.enabled,
                            label = newslettersIntegration.label
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedButton(
                                onClick = onStartNewsletterOAuth,
                                enabled = url.isNotBlank() && !integrationActionRunning,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Connect")
                            }
                            OutlinedButton(
                                onClick = onPreviewNewsletters,
                                enabled = !integrationActionRunning,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Preview")
                            }
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = onClearNewslettersSeen,
                            enabled = !integrationActionRunning,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("Clear Seen")
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
                Divider()
                Spacer(modifier = Modifier.height(12.dp))

                Text(
                    text = "Media",
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                Text(
                    text = "Feeds: $podcastFeedCount podcasts · $youtubeFeedCount YouTube",
                    style = MaterialTheme.typography.bodySmall
                )

                mediaStatus?.let { status ->
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "Queue: ${status.pendingCount} pending, " +
                            "${status.processingCount} processing, " +
                            "${status.completedCount} completed, ${status.failedCount} failed",
                        style = MaterialTheme.typography.bodySmall
                    )
                    status.currentItemTitle?.let { title ->
                        Text(
                            text = "Current: $title",
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }

                if (recentMediaItems.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Recent Items",
                        style = MaterialTheme.typography.labelLarge
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    recentMediaItems.forEach { item ->
                        val typeLabel = when (item.contentType.lowercase()) {
                            "podcast" -> "Podcast"
                            "youtube" -> "YouTube"
                            else -> item.contentType
                        }
                        Text(
                            text = "[$typeLabel • ${item.status}] ${item.title}",
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = onRefreshMediaStatus,
                        enabled = !mediaRefreshing && !integrationActionRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(if (mediaRefreshing) "Refreshing..." else "Refresh")
                    }
                    Button(
                        onClick = onTriggerMediaProcessing,
                        enabled = !mediaTriggering && !integrationActionRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(if (mediaTriggering) "Triggering..." else "Trigger")
                    }
                }
            }
        }
    }
}

@Composable
fun IntegrationStatusRow(
    name: String,
    enabled: Boolean,
    label: String? = null
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Text(
                text = name,
                style = MaterialTheme.typography.bodyMedium
            )
            if (label != null && enabled) {
                Text(
                    text = "Label: $label",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        Text(
            text = if (enabled) "Enabled" else "Not configured",
            style = MaterialTheme.typography.bodySmall,
            color = if (enabled) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.onSurfaceVariant
            }
        )
    }
}

private fun formatUptime(seconds: Int): String {
    val days = seconds / 86400
    val hours = (seconds % 86400) / 3600
    val minutes = (seconds % 3600) / 60

    return when {
        days > 0 -> "${days}d ${hours}h"
        hours > 0 -> "${hours}h ${minutes}m"
        else -> "${minutes}m"
    }
}

@Composable
fun ManualGenerationInput(
    isGenerating: Boolean,
    ghostwriterEnabled: Boolean,
    progress: DigestStatusResponse?,
    error: String?,
    onRunNow: () -> Unit
) {
    Column {
        Button(
            onClick = onRunNow,
            enabled = !isGenerating,
            modifier = Modifier.fillMaxWidth()
        ) {
            if (isGenerating) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    CircularProgressIndicator(
                        modifier = Modifier.height(16.dp).width(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Text("Generating...")
                }
            } else {
                Text("Run Now")
            }
        }

        // Progress indicator for Ghostwriter
        if (isGenerating && ghostwriterEnabled && progress != null) {
            Spacer(modifier = Modifier.height(12.dp))

            // Stage indicator
            Text(
                text = "Stage: ${progress.stage ?: "starting"}",
                style = MaterialTheme.typography.bodyMedium
            )

            Spacer(modifier = Modifier.height(4.dp))

            // Progress bar
            val progressValue = if (progress.progress.totalArticles > 0) {
                progress.progress.articlesEnriched.toFloat() / progress.progress.totalArticles
            } else if (progress.progress.totalFeeds > 0) {
                progress.progress.feedsFetched.toFloat() / progress.progress.totalFeeds
            } else {
                0f
            }

            LinearProgressIndicator(
                progress = progressValue,
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(4.dp))

            // Detailed progress
            Text(
                text = "Feeds: ${progress.progress.feedsFetched}/${progress.progress.totalFeeds} | " +
                        "Articles: ${progress.progress.articlesEnriched}/${progress.progress.totalArticles}",
                style = MaterialTheme.typography.bodySmall
            )
        }

        // Error message
        if (error != null) {
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = error,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error
            )
        }

        Spacer(modifier = Modifier.height(4.dp))

        Text(
            text = if (ghostwriterEnabled) {
                "Generate digest using Ghostwriter server"
            } else {
                "Generate digest locally on this device"
            },
            style = MaterialTheme.typography.bodySmall
        )
    }
}
