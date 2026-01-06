package com.example.epilog

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.example.epilog.service.DigestScheduler
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class EpilogApplication : Application(), Configuration.Provider {

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    @Inject
    lateinit var digestScheduler: DigestScheduler

    override fun onCreate() {
        super.onCreate()
        initializeDigestScheduler()
    }

    private fun initializeDigestScheduler() {
        // Schedule daily digest generation at the configured time
        // This ensures the worker is scheduled even after app updates or device reboots
        digestScheduler.scheduleDailyDigest()
    }

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()
}
