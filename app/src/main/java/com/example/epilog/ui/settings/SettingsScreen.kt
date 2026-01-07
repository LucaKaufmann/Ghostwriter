package com.example.epilog.ui.settings

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
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

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
                .padding(innerPadding)
                .padding(16.dp)
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
                ScheduleInput(
                    hour = uiState.scheduleHour,
                    minute = uiState.scheduleMinute,
                    showTimePicker = uiState.showTimePicker,
                    onShowTimePicker = viewModel::showTimePicker,
                    onHideTimePicker = viewModel::hideTimePicker,
                    onTimeSelected = viewModel::updateScheduleTime
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

            // Manual Run Section
            SettingsSection(title = "Manual Generation") {
                Button(
                    onClick = viewModel::runDigestNow,
                    enabled = !uiState.isGenerating,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (uiState.isGenerating) "Generating..." else "Run Now")
                }
                Text(
                    text = "Generate digest immediately with current settings",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 4.dp)
                )
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScheduleInput(
    hour: Int,
    minute: Int,
    showTimePicker: Boolean,
    onShowTimePicker: () -> Unit,
    onHideTimePicker: () -> Unit,
    onTimeSelected: (Int, Int) -> Unit
) {
    val formattedTime = String.format("%02d:%02d", hour, minute)

    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "Daily digest at",
                    style = MaterialTheme.typography.bodyLarge
                )
                Text(
                    text = formattedTime,
                    style = MaterialTheme.typography.headlineMedium
                )
            }

            OutlinedButton(onClick = onShowTimePicker) {
                Text("Change")
            }
        }

        Text(
            text = "EPUB will be generated daily at this time",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 8.dp)
        )
    }

    if (showTimePicker) {
        TimePickerDialog(
            initialHour = hour,
            initialMinute = minute,
            onDismiss = onHideTimePicker,
            onConfirm = { selectedHour, selectedMinute ->
                onTimeSelected(selectedHour, selectedMinute)
                onHideTimePicker()
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimePickerDialog(
    initialHour: Int,
    initialMinute: Int,
    onDismiss: () -> Unit,
    onConfirm: (Int, Int) -> Unit
) {
    val timePickerState = rememberTimePickerState(
        initialHour = initialHour,
        initialMinute = initialMinute,
        is24Hour = true
    )

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Select Time") },
        text = {
            TimePicker(state = timePickerState)
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onConfirm(timePickerState.hour, timePickerState.minute)
                }
            ) {
                Text("OK")
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
fun MinWordCountInput(
    minWordCount: Int,
    onMinWordCountChange: (Int) -> Unit
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "Minimum word count",
                style = MaterialTheme.typography.bodyLarge
            )
            Text(
                text = if (minWordCount == 0) "Off" else "$minWordCount",
                style = MaterialTheme.typography.bodyLarge
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        Slider(
            value = minWordCount.toFloat(),
            onValueChange = { onMinWordCountChange(it.toInt()) },
            valueRange = 0f..1000f,
            steps = 9,
            modifier = Modifier.fillMaxWidth()
        )

        Text(
            text = "Skip articles shorter than this (0 = include all)",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(top = 4.dp)
        )
    }
}
