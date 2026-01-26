package com.example.epilogue.ui

import android.os.Bundle
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.ui.navigation.EpilogueNavHost
import com.example.epilogue.ui.theme.EpilogueTheme
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var settingsRepository: SettingsRepository

    private val volumeKeyHandler = VolumeKeyHandler()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val einkMode by settingsRepository.einkModeFlow.collectAsState(initial = false)

            EpilogueTheme {
                CompositionLocalProvider(
                    LocalVolumeKeyHandler provides if (einkMode) volumeKeyHandler else null,
                    LocalEinkMode provides einkMode
                ) {
                    EpilogueNavHost(
                        modifier = Modifier.fillMaxSize()
                    )
                }
            }
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        // Only intercept volume keys when e-ink mode is enabled
        if (settingsRepository.getEinkMode()) {
            when (keyCode) {
                KeyEvent.KEYCODE_VOLUME_UP -> {
                    volumeKeyHandler.onVolumeUp()
                    return true
                }
                KeyEvent.KEYCODE_VOLUME_DOWN -> {
                    volumeKeyHandler.onVolumeDown()
                    return true
                }
            }
        }
        return super.onKeyDown(keyCode, event)
    }
}
