package com.example.epilogue.service

import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequest
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.Operation
import com.example.epilogue.domain.model.DigestPeriod
import com.example.epilogue.data.repository.SettingsRepository
import com.google.common.util.concurrent.SettableFuture
import io.mockk.every
import io.mockk.coEvery
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
import kotlinx.coroutines.async
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout

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
            assertEquals(ZoneId.systemDefault().id,
                first.workSpec.input.getString(DailyDigestWorker.KEY_PERIODIC_ZONE))

            val nextDue = before + TimeUnit.HOURS.toMillis(10)
            val oldId = UUID.randomUUID()
            // Unmarked legacy work gains an anchor and zone without changing due time or ID.
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
            assertEquals(ZoneId.systemDefault().id,
                updated.workSpec.input.getString(DailyDigestWorker.KEY_PERIODIC_ZONE))
            verify(exactly = 0) { manager.cancelUniqueWork(workName) }
            scheduler.cancelPeriod(DigestPeriod.MORNING)
            verify(exactly = 1) { manager.cancelUniqueWork(workName) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `boot registration waits for WorkManager persistence receipt`() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val settings = mockk<SettingsRepository>()
        every { settings.getSchedulePeriods() } returns setOf(DigestPeriod.MORNING)
        val receipt = SettableFuture.create<Operation.State.SUCCESS>()
        val operation = mockk<Operation>()
        every { operation.result } returns receipt
        val submitted = CountDownLatch(1)
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns
                MutableStateFlow(emptyList())
            every { manager.enqueueUniquePeriodicWork(workName, any(), any()) } answers {
                submitted.countDown()
                operation
            }
            val scheduler = DigestScheduler(context, settings, mockk(), mockk())
            val registration = async(Dispatchers.IO) { scheduler.scheduleAllPeriodsAwaitPersistence() }
            assertTrue(submitted.await(3, TimeUnit.SECONDS))
            assertFalse(registration.isCompleted)
            receipt.set(Operation.SUCCESS)
            registration.await()
            verify(exactly = 1) { manager.enqueueUniquePeriodicWork(
                workName, ExistingPeriodicWorkPolicy.KEEP, any()) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `period enabled during boot persistence wait remains scheduled`() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val settings = mockk<SettingsRepository>()
        var selected = setOf(DigestPeriod.MORNING)
        every { settings.getSchedulePeriods() } answers { selected }
        coEvery { settings.toggleSchedulePeriod(DigestPeriod.NOON, true) } coAnswers {
            selected = selected + DigestPeriod.NOON
        }
        val receipt = SettableFuture.create<Operation.State.SUCCESS>()
        val morning = mockk<Operation> { every { result } returns receipt }
        val morningSubmitted = CountDownLatch(1)
        val noonSubmitted = CountDownLatch(1)
        val noonName = "daily_digest_NOON"
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(any()) } returns
                MutableStateFlow(emptyList())
            every { manager.enqueueUniquePeriodicWork(any(), any(), any()) } answers {
                if (firstArg<String>() == workName) {
                    morningSubmitted.countDown()
                    morning
                } else {
                    noonSubmitted.countDown()
                    mockk(relaxed = true)
                }
            }
            val scheduler = DigestScheduler(context, settings, mockk(), mockk())
            val boot = async(Dispatchers.IO) { scheduler.scheduleAllPeriodsAwaitPersistence() }
            assertTrue(morningSubmitted.await(3, TimeUnit.SECONDS))
            scheduler.updatePeriod(DigestPeriod.NOON, true)
            assertTrue(noonSubmitted.await(3, TimeUnit.SECONDS))
            receipt.set(Operation.SUCCESS)
            boot.await()
            verify(exactly = 1) { manager.cancelUniqueWork(noonName) }
            verify(exactly = 1) { manager.enqueueUniquePeriodicWork(noonName, any(), any()) }
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `period disabled after boot selection is not re-enqueued by child`() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val settings = mockk<SettingsRepository>()
        lateinit var scheduler: DigestScheduler
        var reads = 0
        every { settings.getSchedulePeriods() } answers {
            if (reads++ == 0) {
                // Return the captured boot snapshot, then complete a user disable
                // before the child allocates its own registration generation.
                scheduler.cancelPeriod(DigestPeriod.MORNING)
                setOf(DigestPeriod.MORNING)
            } else emptySet()
        }
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(any()) } returns
                MutableStateFlow(emptyList())
            scheduler = DigestScheduler(context, settings, mockk(), mockk())
            scheduler.scheduleAllPeriodsAwaitPersistence()
            verify(exactly = 1) { manager.cancelUniqueWork(workName) }
            verify(exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            assertTrue(reads >= 2)
        } finally {
            unmockkStatic(WorkManager::class)
        }
    }

    @Test fun `westbound zone change does not duplicate an anchored occurrence date`() {
        val originalZone = ZoneId.of("Pacific/Kiritimati")
        val westboundZone = ZoneId.of("Pacific/Honolulu")
        val first = ZonedDateTime.of(2026, 9, 27, 7, 0, 0, 0, originalZone)
        val second = first.plusHours(24).toInstant().atZone(westboundZone)
        val anchor = first.toInstant().toEpochMilli()
        assertEquals(LocalDate.of(2026, 9, 27),
            DailyDigestWorker.periodicOccurrenceDate(first, anchor, originalZone))
        assertEquals(LocalDate.of(2026, 9, 28),
            DailyDigestWorker.periodicOccurrenceDate(second, anchor, originalZone))
        assertEquals(LocalDate.of(2026, 9, 27),
            DailyDigestWorker.periodicOccurrenceDate(second, anchor, westboundZone))
    }

    @Test fun `boot does not wait indefinitely for an already running legacy request`() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val manager = mockk<WorkManager>(relaxed = true)
        val settings = mockk<SettingsRepository>()
        every { settings.getSchedulePeriods() } returns setOf(DigestPeriod.MORNING)
        val rows = MutableStateFlow(listOf(info(WorkInfo.State.RUNNING)))
        mockkStatic(WorkManager::class)
        try {
            every { WorkManager.getInstance(context) } returns manager
            every { manager.getWorkInfosForUniqueWorkFlow(workName) } returns rows
            val scheduler = DigestScheduler(context, settings, mockk(), mockk())
            withTimeout(1_000) { scheduler.scheduleAllPeriodsAwaitPersistence() }
            verify(exactly = 0) { manager.enqueueUniquePeriodicWork(workName, any(), any()) }
            scheduler.cancelPeriod(DigestPeriod.MORNING)
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
