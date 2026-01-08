package com.example.epilogue.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.local.FeedDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    private val MIGRATION_1_2 = object : Migration(1, 2) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Create digests table
            database.execSQL("""
                CREATE TABLE IF NOT EXISTS digests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    generatedAt INTEGER NOT NULL,
                    epubFilePath TEXT NOT NULL,
                    articleCount INTEGER NOT NULL,
                    briefingCount INTEGER NOT NULL,
                    fidelityCount INTEGER NOT NULL,
                    triggerType TEXT NOT NULL,
                    feedNames TEXT NOT NULL
                )
            """.trimIndent())

            // Create digest_articles table
            database.execSQL("""
                CREATE TABLE IF NOT EXISTS digest_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    digestId INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    originalUrl TEXT NOT NULL,
                    isSummary INTEGER NOT NULL,
                    feedName TEXT NOT NULL,
                    sortOrder INTEGER NOT NULL,
                    FOREIGN KEY (digestId) REFERENCES digests(id) ON DELETE CASCADE
                )
            """.trimIndent())

            // Create index for foreign key
            database.execSQL(
                "CREATE INDEX IF NOT EXISTS index_digest_articles_digestId ON digest_articles(digestId)"
            )
        }
    }

    private val MIGRATION_2_3 = object : Migration(2, 3) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Add maxArticles column to feeds table with default 0 (unlimited)
            database.execSQL("ALTER TABLE feeds ADD COLUMN maxArticles INTEGER NOT NULL DEFAULT 0")
        }
    }

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): EpilogueDatabase {
        return Room.databaseBuilder(
            context,
            EpilogueDatabase::class.java,
            "epilog_database"
        )
            .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
            .build()
    }

    @Provides
    fun provideFeedDao(database: EpilogueDatabase): FeedDao {
        return database.feedDao()
    }

    @Provides
    fun provideDigestDao(database: EpilogueDatabase): DigestDao {
        return database.digestDao()
    }
}
