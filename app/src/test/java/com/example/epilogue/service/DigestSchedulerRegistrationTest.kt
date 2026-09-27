package com.example.epilogue.service

import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequest
import androidx.work.WorkInfo
import androidx.work.WorkManager
import com.example.epilogue.domain.model.DigestPeriod
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkStatic
import io.mockk.unmockkStatic
import io.mockk.verify
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.onSubscription
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class DigestSchedulerRegistrationTest {
    private val workName = "daily_digest_MORNING"

    private fun info(state: WorkInfo.State, next: Long = Long.MAX_VALUE,
        id: UUID = UUID.randomUUID(), tags: Set<String> = emptySet()): WorkInfo {
        val result = mockk<WorkInfo>()
        every { result.state } returns state
        every { result.nextScheduleTimeMillis } returns next
        every { result.id } returns id
        every { result.tags } returns tags
        return result
    }

    @Test fun `new registration is anchored and first legacy update preserves identity without cancellation`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val rows = MutableStateFlow(emptyList<WorkInfo>())
        val requests = java.util.concurrent.CopyOnWriteArrayList<Pair<ExistingPeriodicWorkPolicy, PeriodicWorkRequest>>()
        val firstSubmitted = CountDownLatch(1)
        val secondSubmitted = CountDownLatch(1)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns rows
            every { manager.enqueueUniquePeriodicWork(workName, any(), any()) } answers {
                requests.add(secondArg<ExistingPeriodicWorkPolicy>() to thirdArg<PeriodicWorkRequest>())
                if (requests.size == 1) firstSubmitted.countDown() else secondSubmitted.countDown()
                mockk(relaxed = true)
            }
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            val before = System.currentTimeMillis()
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            verify(timeout = 3000, exactly = 1) { manager.enqueueUniquePeriodicWork(
                workName, ExistingPeriodicWorkPolicy.KEEP, any()) }
            assertTrue(firstSubmitted.await(3, TimeUnit.SECONDS))
            val first = requests.single().second
            assertEquals("MORNING", first.workSpec.input.getString(DailyDigestWorker.KEY_PERIOD))
            assertTrue(first.workSpec.input.getLong(DailyDigestWorker.KEY_PERIODIC_ANCHOR, 0) > before)
            assertEquals(TimeUnit.HOURS.toMillis(24), first.workSpec.intervalDuration)
            assertTrue(DigestScheduler.ANCHOR_TAG in first.tags)

            val nextDue = before + TimeUnit.HOURS.toMillis(10)
            val oldId = UUID.randomUUID()
            rows.value = listOf(info(WorkInfo.State.ENQUEUED, nextDue, oldId))
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            verify(timeout = 3000, exactly = 1) { manager.enqueueUniquePeriodicWork(
                workName, ExistingPeriodicWorkPolicy.UPDATE, any()) }
            assertTrue(secondSubmitted.await(3, TimeUnit.SECONDS))
            val updated = requests.last().second
            assertEquals(nextDue, updated.workSpec.input.getLong(DailyDigestWorker.KEY_PERIODIC_ANCHOR, 0))
            assertEquals(nextDue, updated.workSpec.nextScheduleTimeOverride)
            assertEquals(oldId, updated.id)
            assertTrue(DigestScheduler.ANCHOR_TAG in updated.tags)
            verify(exactly = 0) { manager.cancelUniqueWork(workName) }
            scheduler.cancelPeriod(DigestPeriod.MORNING)
            verify(exactly = 1) { manager.cancelUniqueWork(workName) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `already anchored request keeps Monday reference after Tuesday midnight delay`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val zone = ZoneId.of("Europe/Zurich")
        val original = ZonedDateTime.of(2026, 3, 9, 20, 0, 0, 0, zone)
        val shiftedNextDue = ZonedDateTime.of(2026, 3, 11, 1, 0, 0, 0, zone)
        val rows = MutableStateFlow(listOf(info(WorkInfo.State.ENQUEUED,
            shiftedNextDue.toInstant().toEpochMilli(), tags = setOf(DigestScheduler.ANCHOR_TAG))))
        val subscriptions = CountDownLatch(2)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns
                rows.onSubscription { subscriptions.countDown() }
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            verify(timeout = 3000, exactly = 1) { manager.getWorkInfosForUniqueWorkFlow(workName) }
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            assertTrue(subscriptions.await(3, TimeUnit.SECONDS))
            verify(timeout = 300, exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            assertEquals(LocalDate.of(2026, 3, 10), DailyDigestWorker.periodicOccurrenceDate(
                shiftedNextDue, original.toInstant().toEpochMilli()))
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `overdue network constrained legacy request is updated in place for same occurrence`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val overdue = System.currentTimeMillis() - TimeUnit.HOURS.toMillis(3)
        val oldId = UUID.randomUUID()
        val rows = MutableStateFlow(listOf(info(WorkInfo.State.ENQUEUED, overdue, oldId)))
        val submitted = java.util.concurrent.atomic.AtomicReference<PeriodicWorkRequest>()
        val submission = CountDownLatch(1)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns rows
            every { manager.enqueueUniquePeriodicWork(workName,
                ExistingPeriodicWorkPolicy.UPDATE, any()) } answers {
                submitted.set(thirdArg())
                submission.countDown()
                mockk(relaxed = true)
            }
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            verify(timeout = 3000) { manager.enqueueUniquePeriodicWork(
                workName, ExistingPeriodicWorkPolicy.UPDATE, any()) }
            assertTrue(submission.await(3, TimeUnit.SECONDS))
            assertEquals(overdue, submitted.get().workSpec.nextScheduleTimeOverride)
            assertEquals(oldId, submitted.get().id)
            assertEquals(overdue, submitted.get().workSpec.input.getLong(
                DailyDigestWorker.KEY_PERIODIC_ANCHOR, 0))
            assertEquals(androidx.work.NetworkType.CONNECTED,
                submitted.get().workSpec.constraints.requiredNetworkType)
            verify(exactly = 0) { manager.cancelUniqueWork(workName) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `running legacy work waits for enqueued state and disable invalidates callback`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val rows = MutableStateFlow(listOf(info(WorkInfo.State.RUNNING)))
        val subscribed = CountDownLatch(1)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns
                rows.onSubscription { subscribed.countDown() }
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            assertTrue(subscribed.await(3, TimeUnit.SECONDS))
            verify(exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            scheduler.cancelPeriod(DigestPeriod.MORNING)
            rows.value = listOf(info(WorkInfo.State.ENQUEUED, System.currentTimeMillis()))
            verify(timeout = 300, exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            verify(exactly = 1) { manager.cancelUniqueWork(workName) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `running legacy work updates when its next iteration is enqueued`() {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val rows = MutableStateFlow(listOf(info(WorkInfo.State.RUNNING)))
        val subscribed = CountDownLatch(1)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns
                rows.onSubscription { subscribed.countDown() }
            val scheduler = DigestScheduler(context, mockk(), mockk(), mockk())
            scheduler.schedulePeriod(DigestPeriod.MORNING)
            assertTrue(subscribed.await(3, TimeUnit.SECONDS))
            verify(exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            rows.value = listOf(info(WorkInfo.State.ENQUEUED, System.currentTimeMillis()))
            verify(timeout = 3000, exactly = 1) { manager.enqueueUniquePeriodicWork(
                workName, ExistingPeriodicWorkPolicy.UPDATE, any()) }
            verify(exactly = 0) { manager.cancelUniqueWork(workName) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }
}
