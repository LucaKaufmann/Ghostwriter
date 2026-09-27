package com.example.epilogue.service

import androidx.work.Data
import androidx.work.ForegroundUpdater
import androidx.work.ListenableWorker
import androidx.work.WorkerParameters
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class FeedSyncWorkerTest {
    private val sync = mockk<FeedSyncV2UseCase>()
    private val store = mockk<AndroidFeedV2Store>()
    private val settings = mockk<SettingsRepository>()

    private fun worker(attempt: Int): FeedSyncWorker {
        val params = mockk<WorkerParameters>(relaxed = true)
        every { params.id } returns UUID.randomUUID()
        every { params.inputData } returns Data.EMPTY
        every { params.runAttemptCount } returns attempt
        val foreground = mockk<ForegroundUpdater>()
        every { foreground.setForegroundAsync(any(), any(), any()) } throws
            IllegalStateException("foreground unavailable in fixture")
        every { params.foregroundUpdater } returns foreground
        return FeedSyncWorker(RuntimeEnvironment.getApplication(), params, sync, store, settings)
    }

    @Test fun `transport and invalid response partials retry but actionable partial completes`() = runBlocking {
        for (phase in listOf("push", "pull", "invalid_response")) {
            coEvery { store.syncAndRecord(sync) } returns FeedSyncV2Outcome.Partial(0, 0, 1, 0, 0, phase)
            assertTrue(worker(0).doWork() is ListenableWorker.Result.Retry)
        }
        coEvery { store.syncAndRecord(sync) } returns FeedSyncV2Outcome.Partial(0, 0, 1, 1, 1, "pending")
        assertTrue(worker(0).doWork() is ListenableWorker.Result.Success)
        coEvery { store.syncAndRecord(sync) } returns FeedSyncV2Outcome.Partial(0, 0, 1, 0, 0, "push")
        assertTrue(worker(FeedSyncWorker.MAX_RETRY_ATTEMPTS).doWork() is ListenableWorker.Result.Failure)
    }
}
