package com.example.epilogue.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.example.epilogue.data.repository.SettingsRepository
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Broadcast receiver that reschedules the daily digest after device boot
 * or app update. This ensures background scheduling persists without
 * requiring the user to manually open the app.
 */
@AndroidEntryPoint
class BootReceiver : BroadcastReceiver() {

    @Inject
    lateinit var digestScheduler: DigestScheduler

    @Inject
    lateinit var settingsRepository: SettingsRepository

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                Log.d(TAG, "Rescheduling after ${intent.action}")
                if (settingsRepository.isGhostwriterConfigured()) {
                    // Ghostwriter handles digest generation, just schedule syncs
                    Log.d(TAG, "Ghostwriter configured, scheduling syncs only")
                    digestScheduler.scheduleFeedSync()
                    digestScheduler.scheduleDigestSync()
                } else {
                    // Local digest generation
                    digestScheduler.scheduleAllPeriods()
                }
            }
        }
    }

    companion object {
        private const val TAG = "BootReceiver"
    }
}
