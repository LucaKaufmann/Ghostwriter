package com.example.epilogue.service

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.example.epilogue.BuildConfig
import com.example.epilogue.R
import com.example.epilogue.data.repository.GhostwriterRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.ui.MainActivity
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class GhostwriterPushMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "GhostwriterPushMessaging"
        private const val CHANNEL_ID = "ghostwriter_digests"
        private const val CHANNEL_NAME = "Digests"
        private const val NOTIFICATION_ID = 2001
    }

    @Inject lateinit var settingsRepository: SettingsRepository
    @Inject lateinit var ghostwriterRepository: GhostwriterRepository
    @Inject lateinit var digestScheduler: DigestScheduler

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)

        if (!settingsRepository.isGhostwriterPushEnabled()) {
            Log.i(TAG, "Push disabled; skipping token registration")
            return
        }

        val deviceId = settingsRepository.getOrCreateGhostwriterDeviceId()
        val appVersion = BuildConfig.VERSION_NAME
        val deviceModel = Build.MODEL

        scope.launch {
            ghostwriterRepository.registerPushDevice(
                deviceId = deviceId,
                token = token,
                appVersion = appVersion,
                deviceModel = deviceModel
            )
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        val data = message.data
        if (data["event"] != "digest_ready") return
        if (!settingsRepository.isGhostwriterPushEnabled()) return

        // Best-effort: show notification (if permitted) and trigger a background sync.
        val title = data["title"] ?: message.notification?.title ?: "New digest available"
        val body = data["body"] ?: message.notification?.body ?: "A new digest is ready to download."

        showNotificationIfPermitted(title, body)
        digestScheduler.syncDigestsNow()
    }

    private fun showNotificationIfPermitted(title: String, body: String) {
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) return

        val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_DEFAULT
            )
            manager.createNotificationChannel(channel)
        }

        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        manager.notify(NOTIFICATION_ID, notification)
    }
}
