package com.example.epilogue.ui

import androidx.compose.runtime.compositionLocalOf
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * Events triggered by volume button presses.
 */
sealed class VolumeKeyEvent {
    data object VolumeUp : VolumeKeyEvent()
    data object VolumeDown : VolumeKeyEvent()
}

/**
 * Handler for volume key events that can be shared across the app.
 */
class VolumeKeyHandler {
    private val _events = MutableSharedFlow<VolumeKeyEvent>(extraBufferCapacity = 1)
    val events: SharedFlow<VolumeKeyEvent> = _events.asSharedFlow()

    fun onVolumeUp() {
        _events.tryEmit(VolumeKeyEvent.VolumeUp)
    }

    fun onVolumeDown() {
        _events.tryEmit(VolumeKeyEvent.VolumeDown)
    }
}

/**
 * CompositionLocal to provide volume key handler to composables.
 */
val LocalVolumeKeyHandler = compositionLocalOf<VolumeKeyHandler?> { null }

/**
 * CompositionLocal to provide e-ink mode state to composables.
 */
val LocalEinkMode = compositionLocalOf { false }
