package com.example.epilogue.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
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

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED -> {
                Log.d(TAG, "Rescheduling digest after ${intent.action}")
                digestScheduler.scheduleDailyDigest()
            }
        }
    }

    companion object {
        private const val TAG = "BootReceiver"
    }
}
