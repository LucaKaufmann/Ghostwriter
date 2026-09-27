package com.example.epilogue.service

import android.content.Context
import androidx.work.impl.WorkManagerImpl
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * WorkManager 2.9 reuses a periodic request UUID across occurrences. Its internal
 * periodCount changes only when an occurrence is acknowledged, not on retry.
 * This read-only adapter is the sole dependency on that internal API. A missing
 * row cannot safely be interpreted as a new occurrence.
 */
internal object PeriodicWorkExecution {
    suspend fun key(context: Context, id: UUID): String? = withContext(Dispatchers.IO) {
        val workSpec = WorkManagerImpl.getInstance(context).workDatabase
            .workSpecDao().getWorkSpec(id.toString()) ?: return@withContext null
        if (!workSpec.isPeriodic) return@withContext null
        key(id, workSpec.periodCount)
    }

    internal fun key(id: UUID, periodCount: Int): String = "$id:$periodCount"
}
