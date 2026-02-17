package com.example.epilogue.shared.ghostwriter

import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.cinterop.BetaInteropApi
import kotlinx.cinterop.addressOf
import kotlinx.cinterop.usePinned
import platform.Foundation.NSData
import platform.Foundation.create

class SharedBinaryBridge {
    @OptIn(ExperimentalForeignApi::class, BetaInteropApi::class)
    fun byteArrayToNSData(bytes: ByteArray): NSData {
        return bytes.usePinned { pinned ->
            NSData.create(bytes = pinned.addressOf(0), length = bytes.size.toULong())
        }
    }
}
