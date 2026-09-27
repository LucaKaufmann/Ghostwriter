package com.example.epilogue.service

import androidx.work.SystemClock
import androidx.work.impl.WorkDatabase
import androidx.work.impl.model.WorkSpec
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class PeriodicWorkExecutionTest {
    @Test fun `pinned WorkManager period counter is stable through retry and advances after acknowledgement`() {
        val db = WorkDatabase.create(RuntimeEnvironment.getApplication(),
            Executor { it.run() }, SystemClock(), true)
        try {
            val id = UUID.randomUUID()
            val spec = WorkSpec(id.toString(), DailyDigestWorker::class.java.name).apply {
                setPeriodic(TimeUnit.HOURS.toMillis(24))
            }
            val dao = db.workSpecDao()
            dao.insertWorkSpec(spec)
            val first = dao.getWorkSpec(id.toString())!!
            assertEquals(0, first.periodCount)
            val firstKey = PeriodicWorkExecution.key(id, first.periodCount)
            dao.incrementWorkSpecRunAttemptCount(id.toString())
            val retry = dao.getWorkSpec(id.toString())!!
            assertEquals(1, retry.runAttemptCount)
            assertEquals(firstKey, PeriodicWorkExecution.key(id, retry.periodCount))
            dao.incrementPeriodCount(id.toString())
            dao.resetWorkSpecRunAttemptCount(id.toString())
            val next = dao.getWorkSpec(id.toString())!!
            assertEquals(1, next.periodCount)
            assertEquals(0, next.runAttemptCount)
            assertEquals("$id:1", PeriodicWorkExecution.key(id, next.periodCount))
        } finally {
            db.close()
        }
    }
}
