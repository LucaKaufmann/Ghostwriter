package com.example.epilog.data.local

import androidx.room.TypeConverter
import com.example.epilog.domain.model.ProcessingMode

class Converters {
    @TypeConverter
    fun fromProcessingMode(mode: ProcessingMode): String = mode.name

    @TypeConverter
    fun toProcessingMode(value: String): ProcessingMode = ProcessingMode.valueOf(value)
}
