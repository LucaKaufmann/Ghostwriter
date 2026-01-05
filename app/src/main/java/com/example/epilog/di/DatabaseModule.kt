package com.example.epilog.di

import android.content.Context
import androidx.room.Room
import com.example.epilog.data.local.EpilogDatabase
import com.example.epilog.data.local.FeedDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): EpilogDatabase {
        return Room.databaseBuilder(
            context,
            EpilogDatabase::class.java,
            "epilog_database"
        ).build()
    }

    @Provides
    fun provideFeedDao(database: EpilogDatabase): FeedDao {
        return database.feedDao()
    }
}
