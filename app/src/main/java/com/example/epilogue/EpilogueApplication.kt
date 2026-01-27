package com.example.epilogue

import android.app.Application
import android.util.Log
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.service.DigestScheduler
import com.example.epilogue.service.EpubExporter
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltAndroidApp
class EpilogueApplication : Application(), Configuration.Provider {

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    @Inject
    lateinit var digestScheduler: DigestScheduler

    @Inject
    lateinit var epubExporter: EpubExporter

    @Inject
    lateinit var settingsRepository: SettingsRepository

    private val applicationScope = CoroutineScope(Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        initializeDigestScheduler()
        initializeGhostwriterSync()
        validateExportPermissions()
    }

    private fun initializeDigestScheduler() {
        // If Ghostwriter is configured, don't schedule local generation
        // Backend handles scheduled digests, we just sync them
        if (settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter configured, skipping local digest scheduling")
            digestScheduler.cancelAllPeriods()
        } else {
            // Schedule local digest generation for all selected periods
            digestScheduler.scheduleAllPeriods()
        }
    }

    private fun initializeGhostwriterSync() {
        // If Ghostwriter is configured, schedule periodic sync and trigger immediate sync
        if (settingsRepository.isGhostwriterConfigured()) {
            Log.i(TAG, "Ghostwriter configured, initializing sync")
            // Schedule and trigger feed sync (bi-directional)
            digestScheduler.scheduleFeedSync()
            digestScheduler.syncFeedsNow()
            // Schedule and trigger digest sync
            digestScheduler.scheduleDigestSync()
            digestScheduler.syncDigestsNow()
        }
    }

    private fun validateExportPermissions() {
        // Validate SAF permissions on startup
        // If permission was revoked, disable custom export
        applicationScope.launch {
            if (!epubExporter.validateStoredPermissions()) {
                Log.w(TAG, "Custom export permission revoked, disabling export")
                settingsRepository.setCustomExportEnabled(false)
            }
        }
    }

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .setMinimumLoggingLevel(android.util.Log.DEBUG)
            .build()

    companion object {
        private const val TAG = "EpilogueApplication"
    }
}
