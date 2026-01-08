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
        validateExportPermissions()
    }

    private fun initializeDigestScheduler() {
        // Schedule daily digest generation at the configured time
        // This ensures the worker is scheduled even after app updates or device reboots
        digestScheduler.scheduleDailyDigest()
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
            .build()

    companion object {
        private const val TAG = "EpilogueApplication"
    }
}
