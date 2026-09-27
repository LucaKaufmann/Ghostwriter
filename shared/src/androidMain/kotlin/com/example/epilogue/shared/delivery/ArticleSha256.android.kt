package com.example.epilogue.shared.delivery

import java.security.MessageDigest

internal actual fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
    .digest(bytes)
    .joinToString("") { "%02x".format(it.toInt() and 0xff) }
