package com.example.epilogue.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.livedata.observeAsState
import androidx.work.WorkInfo
import androidx.work.WorkManager

@Composable
fun SyncStatusIndicator(
    tags: List<String>,
    modifier: Modifier = Modifier
) {
    if (tags.isEmpty()) return

    val context = LocalContext.current
    val workManager = remember(context) { WorkManager.getInstance(context) }

    val workInfos = tags.map { tag ->
        val infos by workManager.getWorkInfosByTagLiveData(tag).observeAsState()
        infos.orEmpty()
    }.flatten()

    val isRunning = workInfos.any { info ->
        info.state == WorkInfo.State.RUNNING || info.state == WorkInfo.State.ENQUEUED
    }
    val hasFailed = workInfos.any { info ->
        info.state == WorkInfo.State.FAILED
    }

    when {
        isRunning -> {
            CircularProgressIndicator(
                strokeWidth = 2.dp,
                modifier = modifier
            )
        }
        hasFailed -> {
            Icon(
                imageVector = Icons.Default.Warning,
                contentDescription = "Sync error",
                tint = MaterialTheme.colorScheme.error,
                modifier = modifier
            )
        }
    }
}
