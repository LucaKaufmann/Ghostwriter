package com.example.epilogue.service

import androidx.work.Configuration
import androidx.work.ListenableWorker
import androidx.work.SystemClock
import androidx.work.impl.WorkDatabase
import androidx.work.impl.WorkerWrapper
import androidx.work.impl.foreground.ForegroundProcessor
import androidx.work.impl.model.WorkSpec
import androidx.work.impl.utils.taskexecutor.WorkManagerTaskExecutor
import android.os.Looper
import com.google.common.util.concurrent.Futures
import io.mockk.every
import io.mockk.mockk
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.TimeUnit
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class PeriodicWorkExecutionTest {
    @Test fun `pinned WorkerWrapper keeps period identity on retry and advances it on success`() {
        val context = RuntimeEnvironment.getApplication()
        val direct = Executor { it.run() }
        val config = Configuration.Builder().setExecutor(direct).setTaskExecutor(direct).build()
        val taskExecutor = WorkManagerTaskExecutor(direct)
        val db = WorkDatabase.create(context, direct, SystemClock(), true)
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
            fun execute(result: ListenableWorker.Result) {
                val worker = mockk<ListenableWorker>(relaxed = true)
                every { worker.isUsed } returns false
                every { worker.startWork() } returns Futures.immediateFuture(result)
                val wrapper = WorkerWrapper.Builder(context, config, taskExecutor,
                    mockk<ForegroundProcessor>(relaxed = true), db,
                    dao.getWorkSpec(id.toString())!!, emptyList())
                    .withWorker(worker).build()
                wrapper.run()
                shadowOf(Looper.getMainLooper()).idle()
                wrapper.future.get(3, TimeUnit.SECONDS)
            }
            execute(ListenableWorker.Result.retry())
            val retry = dao.getWorkSpec(id.toString())!!
            assertEquals(1, retry.runAttemptCount)
            assertEquals(firstKey, PeriodicWorkExecution.key(id, retry.periodCount))
            // Advance the retry's eligibility clock; the wrapper refuses an
            // immediate second run while its backoff window is still pending.
            dao.setLastEnqueueTime(id.toString(),
                System.currentTimeMillis() - TimeUnit.DAYS.toMillis(2))
            execute(ListenableWorker.Result.success())
            val next = dao.getWorkSpec(id.toString())!!
            assertEquals(1, next.periodCount)
            assertEquals(0, next.runAttemptCount)
            assertEquals("$id:1", PeriodicWorkExecution.key(id, next.periodCount))
        } finally {
            db.close()
        }
    }
}
