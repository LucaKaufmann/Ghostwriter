package com.example.epilogue.data.local

import androidx.room.TypeConverter
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.domain.model.TriggerType

class Converters {
    @TypeConverter
    fun fromProcessingMode(mode: ProcessingMode): String = mode.name

    @TypeConverter
    fun toProcessingMode(value: String): ProcessingMode = ProcessingMode.valueOf(value)

    @TypeConverter
    fun fromTriggerType(type: TriggerType): String = type.name

    @TypeConverter
    fun toTriggerType(value: String): TriggerType = TriggerType.valueOf(value)
}
