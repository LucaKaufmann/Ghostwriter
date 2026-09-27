package com.example.epilogue.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters

@Database(
    entities = [FeedEntity::class, DigestEntity::class, DigestArticleEntity::class,
        FeedMutationEntity::class, FeedSyncStateEntity::class],
    version = 9,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class EpilogueDatabase : RoomDatabase() {
    abstract fun feedDao(): FeedDao
    abstract fun digestDao(): DigestDao
    abstract fun feedMutationDao(): FeedMutationDao
    abstract fun feedSyncStateDao(): FeedSyncStateDao
}
