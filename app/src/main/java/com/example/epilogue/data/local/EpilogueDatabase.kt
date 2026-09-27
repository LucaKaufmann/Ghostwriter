package com.example.epilogue.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters

@Database(
    entities = [FeedEntity::class, DigestEntity::class, DigestArticleEntity::class,
        FeedMutationEntity::class, FeedSyncStateEntity::class,
        ArticleDeliveryEntity::class, GenerationRunEntity::class],
    version = 10,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class EpilogueDatabase : RoomDatabase() {
    abstract fun feedDao(): FeedDao
    abstract fun digestDao(): DigestDao
    abstract fun feedMutationDao(): FeedMutationDao
    abstract fun feedSyncStateDao(): FeedSyncStateDao
    abstract fun articleDeliveryDao(): ArticleDeliveryDao
    abstract fun generationRunDao(): GenerationRunDao
}
