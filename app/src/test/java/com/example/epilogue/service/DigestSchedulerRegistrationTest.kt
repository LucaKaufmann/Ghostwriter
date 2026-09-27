package com.example.epilogue.service

import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequest
import androidx.work.WorkManager
import com.example.epilogue.domain.model.DigestPeriod
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkStatic
import io.mockk.unmockkStatic
import io.mockk.verify
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class DigestSchedulerRegistrationTest {
    @Test fun `registration preserves existing anchor and cancels legacy and current schedules on disable`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val requests = mutableListOf<PeriodicWorkRequest>()
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.enqueueUniquePeriodicWork("daily_digest_anchored_MORNING",
                ExistingPeriodicWorkPolicy.KEEP, capture(requests)) } returns mockk(relaxed = true)
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            val before = System.currentTimeMillis()
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            assertEquals(2, requests.size)
            for (request in requests) {
                assertEquals("MORNING", request.workSpec.input.getString(DailyDigestWorker.KEY_PERIOD))
                assertTrue(request.workSpec.input.getLong(DailyDigestWorker.KEY_PERIODIC_ANCHOR, 0) > before)
                assertEquals(24L * 60 * 60 * 1000, request.workSpec.intervalDuration)
            }
            verify(exactly = 2) { manager.enqueueUniquePeriodicWork(
                "daily_digest_anchored_MORNING", ExistingPeriodicWorkPolicy.KEEP, any()) }
            scheduler.cancelPeriod(DigestPeriod.MORNING)
            verify(exactly = 3) { manager.cancelUniqueWork("daily_digest_MORNING") }
            verify(exactly = 1) { manager.cancelUniqueWork("daily_digest_anchored_MORNING") }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }
}
