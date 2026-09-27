package com.example.epilogue.ui.settings

import android.os.Looper
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModelStore
import androidx.work.Data
import androidx.work.WorkInfo
import com.example.epilogue.data.repository.DigestRepository
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.data.local.GenerationRunDao
import com.example.epilogue.data.local.GenerationRunEntity
import com.example.epilogue.service.ConfigSyncManager
import com.example.epilogue.service.DigestScheduler
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import java.util.UUID

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class SettingsViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private val settings = mockk<SettingsRepository>(relaxed = true)
    private val scheduler = mockk<DigestScheduler>(relaxed = true)
    private val digests = mockk<DigestRepository>(relaxed = true)
    private val feeds = mockk<FeedRepository>(relaxed = true)
    private val ghostwriter = mockk<GhostwriterRepository>(relaxed = true)
    private val configSync = mockk<ConfigSyncManager>(relaxed = true)
    private val feedSyncV2 = mockk<FeedSyncV2UseCase>(relaxed = true)
    private val feedV2Store = mockk<AndroidFeedV2Store>(relaxed = true)
    private val generationRunDao = mockk<GenerationRunDao>()

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        every { settings.isGhostwriterConfigured() } returns false
        every { settings.isGhostwriterEnabled() } returns false
        every { settings.getGhostwriterUrl() } returns null
        every { generationRunDao.observeLatestFinished() } returns flowOf(null)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun viewModel() = SettingsViewModel(settings, scheduler, digests, feeds,
        ghostwriter, configSync, feedSyncV2, feedV2Store, generationRunDao)

    private fun workInfo(id: UUID, state: WorkInfo.State) =
        WorkInfo(id, state, emptySet(), Data.EMPTY)

    private fun emit(data: MutableLiveData<WorkInfo>, info: WorkInfo?) {
        data.postValue(info)
        shadowOf(Looper.getMainLooper()).idle()
    }

    @Test
    fun `scheduled local run diagnostics appear without manual WorkInfo and survive view model recreation`() = runTest {
        val latest = MutableStateFlow<GenerationRunEntity?>(null)
        every { generationRunDao.observeLatestFinished() } returns latest
        val first = viewModel()
        advanceUntilIdle()
        latest.value = GenerationRunEntity(runId = 4, startedAt = 1, finishedAt = 2,
            outcome = "deferred", diagnosticsJson =
                """{"delivered_count":0,"filtered_count":2,"cap_deferred_count":3,"failed_count":0,"reason_counts":{"content_too_short":2}}""")
        advanceUntilIdle()
        assertTrue(first.uiState.value.localRunSummary!!.title.contains("Deferred"))
        val reopened = viewModel()
        advanceUntilIdle()
        assertTrue(reopened.uiState.value.localRunSummary!!.counts.contains("Waiting 3"))
        assertTrue(reopened.uiState.value.localRunSummary!!.reasons!!.contains("minimum word count"))
    }

    @Test
    fun `replacement detaches prior run and ignores its terminal result`() {
        val first = UUID.randomUUID()
        val second = UUID.randomUUID()
        val firstData = MutableLiveData<WorkInfo>()
        val secondData = MutableLiveData<WorkInfo>()
        every { scheduler.runNow(false) } returnsMany listOf(first, second)
        every { scheduler.getImmediateWorkInfo(first) } returns firstData
        every { scheduler.getImmediateWorkInfo(second) } returns secondData
        val model = viewModel()

        model.runDigestNow()
        assertTrue(firstData.hasObservers())
        model.runDigestNow()
        assertFalse(firstData.hasObservers())
        assertTrue(secondData.hasObservers())

        emit(firstData, workInfo(first, WorkInfo.State.SUCCEEDED))
        emit(secondData, workInfo(first, WorkInfo.State.SUCCEEDED))
        assertTrue(model.uiState.value.isGenerating)
        assertFalse(model.uiState.value.digestCompleted)
        emit(secondData, workInfo(second, WorkInfo.State.SUCCEEDED))
        assertFalse(model.uiState.value.isGenerating)
        assertTrue(model.uiState.value.digestCompleted)
        assertFalse(secondData.hasObservers())
        verify(exactly = 2) { scheduler.runNow(false) }
    }

    @Test
    fun `null before asynchronous enqueue leaves observation active`() {
        val id = UUID.randomUUID()
        val data = MutableLiveData<WorkInfo>()
        every { scheduler.runNow(false) } returns id
        every { scheduler.getImmediateWorkInfo(id) } returns data
        val model = viewModel()
        emit(data, null)
        model.runDigestNow()
        assertTrue(model.uiState.value.isGenerating)
        assertTrue(data.hasObservers())
        emit(data, null)
        emit(data, workInfo(id, WorkInfo.State.SUCCEEDED))
        assertTrue(model.uiState.value.digestCompleted)
        assertFalse(data.hasObservers())
    }

    @Test
    fun `each terminal outcome clears progress and stale flags`() {
        for (state in listOf(WorkInfo.State.SUCCEEDED, WorkInfo.State.FAILED, WorkInfo.State.CANCELLED)) {
            val id = UUID.randomUUID()
            val nextId = UUID.randomUUID()
            val data = MutableLiveData<WorkInfo>()
            val nextData = MutableLiveData<WorkInfo>()
            every { scheduler.runNow(false) } returnsMany listOf(id, nextId)
            every { scheduler.getImmediateWorkInfo(id) } returns data
            every { scheduler.getImmediateWorkInfo(nextId) } returns nextData
            val model = viewModel()
            model.runDigestNow()
            emit(data, workInfo(id, state))
            assertFalse(model.uiState.value.isGenerating)
            assertTrue(model.uiState.value.digestCompleted == (state == WorkInfo.State.SUCCEEDED))
            assertTrue(model.uiState.value.digestFailed == (state == WorkInfo.State.FAILED))
            assertFalse(data.hasObservers())

            model.runDigestNow()
            assertFalse(model.uiState.value.digestCompleted)
            assertFalse(model.uiState.value.digestFailed)
            assertTrue(model.uiState.value.isGenerating)
        }
    }

    @Test
    fun `disposal removes observation without cancelling durable work`() {
        val id = UUID.randomUUID()
        val data = MutableLiveData<WorkInfo>()
        every { scheduler.runNow(false) } returns id
        every { scheduler.getImmediateWorkInfo(id) } returns data
        val model = viewModel()
        val store = ViewModelStore()
        store.put("settings", model)
        model.runDigestNow()
        store.clear()
        assertFalse(data.hasObservers())
        verify(exactly = 0) { scheduler.cancelAllPeriods() }
    }

    @Test
    fun `persisted enabled Ghostwriter uses backend path`() = runTest(dispatcher) {
        every { settings.isGhostwriterEnabled() } returns true
        every { settings.getGhostwriterUrl() } returns "https://fixture.invalid"
        coEvery { feedSyncV2.sync() } returns FeedSyncV2Outcome.NotConfigured
        val model = viewModel()
        model.runDigestNow()
        advanceUntilIdle()
        coVerify(exactly = 1) { feedSyncV2.sync() }
        coVerify(exactly = 0) { ghostwriter.syncFeeds(any()) }
        verify(exactly = 0) { scheduler.runNow(any()) }
        assertFalse(model.uiState.value.isGenerating)
    }

    @Test
    fun `regeneration follows visible local fallback when backend URL is blank`() = runTest(dispatcher) {
        every { settings.isGhostwriterEnabled() } returns true
        every { settings.getGhostwriterUrl() } returns "   "
        val id = UUID.randomUUID()
        every { scheduler.runNow(true) } returns id
        every { scheduler.getImmediateWorkInfo(id) } returns MutableLiveData()
        val model = viewModel()
        advanceUntilIdle()

        model.regenerateDigestLocally()

        verify(exactly = 1) { scheduler.runNow(true) }
        assertTrue(model.uiState.value.isGenerating)
    }
}
