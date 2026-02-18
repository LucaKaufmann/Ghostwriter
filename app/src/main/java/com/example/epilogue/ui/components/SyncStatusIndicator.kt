package com.example.epilogue.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
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
import com.example.epilogue.ui.LocalEinkMode

@Composable
fun SyncStatusIndicator(
    tags: List<String>,
    modifier: Modifier = Modifier
) {
    if (tags.isEmpty()) return

    val context = LocalContext.current
    val einkMode = LocalEinkMode.current
    val workManager = remember(context) { WorkManager.getInstance(context) }

    val workInfos = tags.map { tag ->
        val infos by workManager.getWorkInfosByTagLiveData(tag).observeAsState()
        infos.orEmpty()
    }.flatten()

    val isRunning = workInfos.any { info ->
        info.state == WorkInfo.State.RUNNING
    }
    val hasFailed = workInfos.any { info ->
        info.state == WorkInfo.State.FAILED
    }

    when {
        isRunning -> {
            if (einkMode) {
                Icon(
                    imageVector = Icons.Default.Sync,
                    contentDescription = "Sync in progress",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = modifier
                )
            } else {
                CircularProgressIndicator(
                    strokeWidth = 2.dp,
                    modifier = modifier
                )
            }
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
