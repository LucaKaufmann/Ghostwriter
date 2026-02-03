package com.example.epilogue.data.local

import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.domain.model.TriggerType
import org.junit.Assert.assertEquals
import org.junit.Test

class ConvertersTest {

    private val converters = Converters()

    @Test
    fun `processing mode round trip`() {
        val value = ProcessingMode.BRIEFING
        val stored = converters.fromProcessingMode(value)
        val restored = converters.toProcessingMode(stored)

        assertEquals(value, restored)
    }

    @Test
    fun `trigger type round trip`() {
        val value = TriggerType.SCHEDULED
        val stored = converters.fromTriggerType(value)
        val restored = converters.toTriggerType(stored)

        assertEquals(value, restored)
    }
}
