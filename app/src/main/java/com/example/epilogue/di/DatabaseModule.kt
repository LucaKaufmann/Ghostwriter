package com.example.epilogue.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.example.epilogue.data.local.DigestDao
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.local.FeedDao
import com.example.epilogue.data.local.FeedMutationDao
import com.example.epilogue.data.local.FeedSyncStateDao
import com.example.epilogue.data.local.ArticleDeliveryDao
import com.example.epilogue.data.local.GenerationRunDao
import org.json.JSONObject
import java.util.UUID
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

    private val MIGRATION_3_4 = object : Migration(3, 4) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Add remoteId column to digests table for Ghostwriter sync
            database.execSQL("ALTER TABLE digests ADD COLUMN remoteId TEXT DEFAULT NULL")
        }
    }

    private val MIGRATION_4_5 = object : Migration(4, 5) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Add sync fields for bi-directional feed sync with Ghostwriter
            database.execSQL(
                "ALTER TABLE feeds ADD COLUMN serverUpdatedAt INTEGER DEFAULT NULL"
            )
            database.execSQL(
                "ALTER TABLE feeds ADD COLUMN locallyModified INTEGER NOT NULL DEFAULT 0"
            )
        }
    }

    private val MIGRATION_5_6 = object : Migration(5, 6) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Add period field to digests (morning, noon, evening, manual)
            database.execSQL(
                "ALTER TABLE digests ADD COLUMN period TEXT DEFAULT NULL"
            )
        }
    }

    private val MIGRATION_6_7 = object : Migration(6, 7) {
        override fun migrate(database: SupportSQLiteDatabase) {
            // Add feed enabled/disabled state for Ghostwriter parity.
            database.execSQL(
                "ALTER TABLE feeds ADD COLUMN isEnabled INTEGER NOT NULL DEFAULT 1"
            )
        }
    }

    private val MIGRATION_7_8 = object : Migration(7, 8) {
        override fun migrate(database: SupportSQLiteDatabase) {
            database.execSQL(
                "ALTER TABLE digests ADD COLUMN isComplete INTEGER NOT NULL DEFAULT 1"
            )
            database.execSQL(
                "ALTER TABLE digests ADD COLUMN errorMessage TEXT DEFAULT NULL"
            )
        }
    }

    /** Preserves every installed feed as a proposal until a complete v2 reconciliation. */
    val MIGRATION_8_9 = object : Migration(8, 9) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE feeds ADD COLUMN serverId TEXT")
            db.execSQL("ALTER TABLE feeds ADD COLUMN serverVersion INTEGER")
            db.execSQL("ALTER TABLE feeds ADD COLUMN mutationRevision INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE feeds ADD COLUMN hiddenDelete INTEGER NOT NULL DEFAULT 0")
            db.execSQL("ALTER TABLE feeds ADD COLUMN serverSnapshotJson TEXT")
            db.execSQL("""CREATE TABLE IF NOT EXISTS feed_mutations (
                opId TEXT NOT NULL PRIMARY KEY, serverKey TEXT NOT NULL, url TEXT NOT NULL,
                kind TEXT NOT NULL, baseVersion INTEGER, fieldsJson TEXT NOT NULL,
                localRevision INTEGER NOT NULL, state TEXT NOT NULL, serverSnapshotJson TEXT,
                createdAt INTEGER NOT NULL, sequence INTEGER NOT NULL, queueOrder INTEGER NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0,
                rejectionCode TEXT, rejectionMessage TEXT
            )""".trimIndent())
            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS index_feed_mutations_serverKey_url_sequence ON feed_mutations(serverKey,url,sequence)")
            db.execSQL("""CREATE TABLE IF NOT EXISTS feed_sync_state (
                serverKey TEXT NOT NULL PRIMARY KEY, bindingUrl TEXT, configurationId TEXT,
                serverInstanceId TEXT, cursorVersion INTEGER, firstBindingComplete INTEGER NOT NULL,
                nextSequence INTEGER NOT NULL, generation INTEGER NOT NULL, active INTEGER NOT NULL,
                suspended INTEGER NOT NULL, lastOutcome TEXT, lastDiagnostic TEXT
            )""".trimIndent())
            var sequence = 1L
            db.query("SELECT url,name,mode,maxArticles,isEnabled FROM feeds WHERE url NOT LIKE 'synthetic://%' ORDER BY url").use { rows ->
                while (rows.moveToNext()) {
                    val fields = JSONObject()
                        .put("title", rows.getString(1))
                        .put("mode", if (rows.getString(2) == "BRIEFING") "summarize" else "raw")
                        .put("max_articles", rows.getInt(3))
                        .put("is_active", rows.getInt(4) != 0)
                    db.execSQL("""INSERT INTO feed_mutations
                        (opId,serverKey,url,kind,baseVersion,fieldsJson,localRevision,state,
                         serverSnapshotJson,createdAt,sequence,queueOrder,sent,rejectionCode,rejectionMessage)
                        VALUES (?,?,?,'upsert',NULL,?,0,'legacy_unresolved',NULL,0,?,?,0,NULL,NULL)
                    """.trimIndent(), arrayOf(UUID.randomUUID().toString(), "unbound", rows.getString(0), fields.toString(), sequence, sequence))
                    sequence++
                }
            }
            db.execSQL("""INSERT INTO feed_sync_state
                (serverKey,bindingUrl,configurationId,serverInstanceId,cursorVersion,
                 firstBindingComplete,nextSequence,generation,active,suspended,lastOutcome,lastDiagnostic)
                VALUES ('unbound',NULL,NULL,NULL,NULL,0,?,0,0,0,NULL,NULL)
            """.trimIndent(), arrayOf(sequence))
        }
    }

    /** Prior associations have no provable feed URL; preserve them without guessed claims. */
    val MIGRATION_9_10 = object : Migration(9, 10) {
        override fun migrate(db: SupportSQLiteDatabase) {
            db.execSQL("ALTER TABLE digest_articles ADD COLUMN feedUrl TEXT")
            db.execSQL("""CREATE TABLE IF NOT EXISTS article_delivery (
                feedUrl TEXT NOT NULL, articleKey TEXT NOT NULL, state TEXT NOT NULL,
                reason TEXT, filterSignature TEXT, lastAttemptSequence INTEGER NOT NULL,
                firstDigestId INTEGER, committedAt INTEGER NOT NULL,
                PRIMARY KEY(feedUrl, articleKey),
                CHECK(state IN ('retryable','delivered','excluded'))
            )""".trimIndent())
            db.execSQL("""CREATE TABLE IF NOT EXISTS generation_runs (
                runId INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                startedAt INTEGER NOT NULL, finishedAt INTEGER, outcome TEXT NOT NULL,
                digestId INTEGER, diagnosticsJson TEXT NOT NULL,
                regeneration INTEGER NOT NULL
            )""".trimIndent())
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
            .addMigrations(
                MIGRATION_1_2,
                MIGRATION_2_3,
                MIGRATION_3_4,
                MIGRATION_4_5,
                MIGRATION_5_6,
                MIGRATION_6_7,
                MIGRATION_7_8,
                MIGRATION_8_9,
                MIGRATION_9_10
            )
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

    @Provides
    fun provideFeedMutationDao(database: EpilogueDatabase): FeedMutationDao = database.feedMutationDao()

    @Provides
    fun provideFeedSyncStateDao(database: EpilogueDatabase): FeedSyncStateDao = database.feedSyncStateDao()

    @Provides
    fun provideArticleDeliveryDao(database: EpilogueDatabase): ArticleDeliveryDao = database.articleDeliveryDao()

    @Provides
    fun provideGenerationRunDao(database: EpilogueDatabase): GenerationRunDao = database.generationRunDao()
}
