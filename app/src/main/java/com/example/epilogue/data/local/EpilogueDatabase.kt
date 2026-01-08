package com.example.epilogue.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters

@Database(
    entities = [FeedEntity::class, DigestEntity::class, DigestArticleEntity::class],
    version = 3,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class EpilogueDatabase : RoomDatabase() {
    abstract fun feedDao(): FeedDao
    abstract fun digestDao(): DigestDao
}
