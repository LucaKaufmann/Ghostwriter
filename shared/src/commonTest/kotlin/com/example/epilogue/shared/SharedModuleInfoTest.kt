package com.example.epilogue.shared

import kotlin.test.Test
import kotlin.test.assertEquals

class SharedModuleInfoTest {
    @Test
    fun defaultValuesRemainStable() {
        val info = SharedModuleInfo()
        assertEquals("EpilogueShared", info.name)
        assertEquals("0.1.0", info.version)
    }
}
