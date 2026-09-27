package com.example.epilogue.data.local

import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteConstraintException
import androidx.room.Room
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File

/** An isolated feasibility probe anchored to the deployed Room 8 schema. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class Room8UpgradeProbeTest {
    @get:Rule val files = TemporaryFolder()

    private val context get() = RuntimeEnvironment.getApplication()
    private val name get() = "room-8-probe-${files.root.name}.db"
    private val path get() = context.getDatabasePath(name)
    private lateinit var artifact: File

    private fun room8(): LegacyRoom8Database =
        Room.databaseBuilder(context, LegacyRoom8Database::class.java, name)
            .allowMainThreadQueries()
            .build()

    private fun createFixture() {
        context.deleteDatabase(name)
        artifact = files.newFile("fixture.epub").apply { writeText("synthetic EPUB bytes") }
        val db = room8()
        val sql = db.openHelper.writableDatabase
        sql.execSQL("""INSERT INTO feeds
            (url,name,mode,lastFetched,maxArticles,isEnabled,serverUpdatedAt,locallyModified)
            VALUES (?,?,?,?,?,?,?,?)
        """.trimIndent(), arrayOf("https://example.org/unchanged", "Local title", "FIDELITY", 1234L, 0, 1, 77L, 0))
        sql.execSQL("""INSERT INTO feeds
            (url,name,mode,lastFetched,maxArticles,isEnabled,serverUpdatedAt,locallyModified)
            VALUES (?,?,?,?,?,?,?,?)
        """.trimIndent(), arrayOf("https://example.org/dirty", "Edited title", "BRIEFING", 9876L, 4, 0, 88L, 1))
        sql.execSQL("""INSERT INTO feeds
            (url,name,mode,lastFetched,maxArticles,isEnabled,serverUpdatedAt,locallyModified)
            VALUES (?,?,?,?,?,?,?,?)
        """.trimIndent(), arrayOf("synthetic://wallabag", "Wallabag", "FIDELITY", 55L, 0, 1, null, 1))
        sql.execSQL("""INSERT INTO digests
            (id,generatedAt,epubFilePath,articleCount,briefingCount,fidelityCount,
             triggerType,feedNames,remoteId,period,isComplete,errorMessage)
            VALUES (1,100,?,1,0,1,'MANUAL','Local title',NULL,'manual',1,NULL)
        """.trimIndent(), arrayOf(artifact.absolutePath))
        sql.execSQL("""INSERT INTO digest_articles
            (id,digestId,title,author,content,originalUrl,isSummary,feedName,sortOrder)
            VALUES (1,1,'Kept article','Author','Synthetic content',
                    'https://example.org/article',0,'Local title',0)
        """.trimIndent())
        db.close()
    }

    private fun SQLiteDatabase.scalar(sql: String): String? = rawQuery(sql, null).use {
        if (it.moveToFirst() && !it.isNull(0)) it.getString(0) else null
    }

    @Test fun `frozen Room 8 file matches deployed identity and reopens intact`() {
        createFixture()
        assertTrue(path.isFile)
        val reopened = room8()
        assertEquals(8, reopened.openHelper.readableDatabase.version)
        reopened.close()
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { sql ->
            assertDeployedRoom8Shape(sql)
            assertEquals("3", sql.scalar("SELECT COUNT(*) FROM feeds"))
            assertEquals("1234", sql.scalar("SELECT lastFetched FROM feeds WHERE url='https://example.org/unchanged'"))
            assertEquals("0", sql.scalar("SELECT locallyModified FROM feeds WHERE url='https://example.org/unchanged'"))
            assertEquals("1", sql.scalar("SELECT locallyModified FROM feeds WHERE url='https://example.org/dirty'"))
            assertEquals(artifact.absolutePath, sql.scalar("SELECT epubFilePath FROM digests WHERE id=1"))
            assertEquals("Kept article", sql.scalar("SELECT title FROM digest_articles WHERE digestId=1"))
        }
        assertEquals("synthetic EPUB bytes", artifact.readText())
    }

    @Test fun `additive probe preserves every legacy proposal and existing rows`() {
        createFixture()
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
            probeMigration(db)
            assertEquals(9, db.version)
            assertEquals("3", db.scalar("SELECT COUNT(*) FROM feeds"))
            assertEquals("1", db.scalar("SELECT COUNT(*) FROM digests"))
            assertEquals("1", db.scalar("SELECT COUNT(*) FROM digest_articles"))
            assertEquals(artifact.absolutePath, db.scalar("SELECT epubFilePath FROM digests"))
            assertEquals("synthetic EPUB bytes", artifact.readText())
            assertEquals("Kept article", db.scalar("SELECT title FROM digest_articles"))
            assertEquals("2", db.scalar("SELECT COUNT(*) FROM feed_mutations"))
            assertEquals("0", db.scalar("SELECT COUNT(*) FROM feed_mutations WHERE url LIKE 'synthetic://%'"))
            assertEquals("1234", db.scalar("SELECT lastFetched FROM feeds WHERE url='https://example.org/unchanged'"))
            assertEquals("9876", db.scalar("SELECT lastFetched FROM feeds WHERE url='https://example.org/dirty'"))
            assertEquals("0", db.scalar("SELECT locallyModified FROM feeds WHERE url='https://example.org/unchanged'"))
            assertEquals("1", db.scalar("SELECT locallyModified FROM feeds WHERE url='https://example.org/dirty'"))
            assertEquals("0", db.scalar("SELECT mutationRevision FROM feeds WHERE url='https://example.org/dirty'"))
            assertNull(db.scalar("SELECT serverVersion FROM feeds WHERE url='https://example.org/dirty'"))
            assertEquals("3", db.scalar("SELECT nextSequence FROM feed_sync_state WHERE serverKey='unbound'"))
            assertNull(db.scalar("SELECT serverInstanceId FROM feed_sync_state WHERE serverKey='unbound'"))
            assertEquals("0", db.scalar("SELECT firstBindingComplete FROM feed_sync_state WHERE serverKey='unbound'"))
            assertEquals("1", db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='index_feed_mutations_serverKey_url_sequence'"))
            db.rawQuery("SELECT url, fieldsJson, state, sent, sequence FROM feed_mutations ORDER BY sequence", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("https://example.org/dirty", rows.getString(0))
                assertEquals("legacy_unresolved", rows.getString(2))
                assertEquals(0, rows.getInt(3))
                assertEquals(1L, rows.getLong(4))
                val dirty = JSONObject(rows.getString(1))
                assertEquals("Edited title", dirty.getString("title"))
                assertEquals("briefing", dirty.getString("mode"))
                assertEquals(4, dirty.getInt("max_articles"))
                assertFalse(dirty.getBoolean("is_active"))
                assertTrue(rows.moveToNext())
                assertEquals("https://example.org/unchanged", rows.getString(0))
                val unchanged = JSONObject(rows.getString(1))
                assertEquals("Local title", unchanged.getString("title"))
                assertEquals(0, unchanged.getInt("max_articles"))
                assertTrue(unchanged.getBoolean("is_active"))
                assertFalse(rows.moveToNext())
            }
            assertThrows(SQLiteConstraintException::class.java) {
                db.execSQL("""INSERT INTO feed_mutations
                    (opId,serverKey,url,kind,fieldsJson,localRevision,state,createdAt,sequence,sent)
                    VALUES ('duplicate','unbound','https://example.org/dirty','upsert','{}',0,'queued',0,1,0)
                """.trimIndent())
            }
            db.execSQL("DELETE FROM feed_mutations WHERE url='https://example.org/dirty'")
            db.execSQL("INSERT INTO feed_sync_state (serverKey,nextSequence) VALUES ('other-server',1)")
            assertEquals("3", db.scalar("SELECT nextSequence FROM feed_sync_state WHERE serverKey='unbound'"))
            assertEquals("1", db.scalar("SELECT nextSequence FROM feed_sync_state WHERE serverKey='other-server'"))
        }
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { reopened ->
            assertEquals(9, reopened.version)
            assertEquals("3", reopened.scalar("SELECT nextSequence FROM feed_sync_state WHERE serverKey='unbound'"))
            assertEquals("1", reopened.scalar("SELECT COUNT(*) FROM digest_articles"))
        }
    }

    @Test fun `failed probe rolls back DDL and original Room 8 file reopens`() {
        createFixture()
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
            assertThrows(IllegalStateException::class.java) { probeMigration(db, failAfterAlter = true) }
            assertEquals(8, db.version)
            assertEquals("0", db.scalar("SELECT COUNT(*) FROM pragma_table_info('feeds') WHERE name='serverVersion'"))
            assertEquals("0", db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE name='feed_mutations'"))
        }
        val reopened = room8()
        assertEquals(8, reopened.openHelper.readableDatabase.version)
        reopened.close()
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { sql ->
            assertDeployedRoom8Shape(sql)
            assertEquals("Edited title", sql.scalar("SELECT name FROM feeds WHERE url='https://example.org/dirty'"))
            assertEquals("1", sql.scalar("SELECT COUNT(*) FROM digests"))
        }
        assertEquals("synthetic EPUB bytes", artifact.readText())
    }

    private fun assertDeployedRoom8Shape(db: SQLiteDatabase) {
        assertEquals("12f91675bc2dd3666434a820d81e3318",
            db.scalar("SELECT identity_hash FROM room_master_table WHERE id=42"))
        assertEquals(
            "CREATE TABLE `feeds` (`url` TEXT NOT NULL, `name` TEXT NOT NULL, `mode` TEXT NOT NULL, `lastFetched` INTEGER NOT NULL, `maxArticles` INTEGER NOT NULL, `isEnabled` INTEGER NOT NULL, `serverUpdatedAt` INTEGER, `locallyModified` INTEGER NOT NULL, PRIMARY KEY(`url`))",
            db.scalar("SELECT sql FROM sqlite_master WHERE type='table' AND name='feeds'")
        )
        assertEquals(
            "CREATE TABLE `digests` (`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, `generatedAt` INTEGER NOT NULL, `epubFilePath` TEXT NOT NULL, `articleCount` INTEGER NOT NULL, `briefingCount` INTEGER NOT NULL, `fidelityCount` INTEGER NOT NULL, `triggerType` TEXT NOT NULL, `feedNames` TEXT NOT NULL, `remoteId` TEXT, `period` TEXT, `isComplete` INTEGER NOT NULL, `errorMessage` TEXT)",
            db.scalar("SELECT sql FROM sqlite_master WHERE type='table' AND name='digests'")
        )
        assertEquals(
            "CREATE TABLE `digest_articles` (`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, `digestId` INTEGER NOT NULL, `title` TEXT NOT NULL, `author` TEXT NOT NULL, `content` TEXT NOT NULL, `originalUrl` TEXT NOT NULL, `isSummary` INTEGER NOT NULL, `feedName` TEXT NOT NULL, `sortOrder` INTEGER NOT NULL, FOREIGN KEY(`digestId`) REFERENCES `digests`(`id`) ON UPDATE NO ACTION ON DELETE CASCADE )",
            db.scalar("SELECT sql FROM sqlite_master WHERE type='table' AND name='digest_articles'")
        )
        assertEquals(
            "CREATE INDEX `index_digest_articles_digestId` ON `digest_articles` (`digestId`)",
            db.scalar("SELECT sql FROM sqlite_master WHERE type='index' AND name='index_digest_articles_digestId'")
        )
        assertEquals("3", db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('feeds','digests','digest_articles')"))
        assertEquals("1", db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='index_digest_articles_digestId'"))
        assertEquals("8", db.scalar("SELECT COUNT(*) FROM pragma_table_info('feeds')"))
        assertEquals("12", db.scalar("SELECT COUNT(*) FROM pragma_table_info('digests')"))
        assertEquals("9", db.scalar("SELECT COUNT(*) FROM pragma_table_info('digest_articles')"))
        assertEquals("CASCADE", db.scalar("SELECT on_delete FROM pragma_foreign_key_list('digest_articles')"))
    }

    /** Test-only DDL and backfill shape for the later production Migration(8, 9). */
    private fun probeMigration(db: SQLiteDatabase, failAfterAlter: Boolean = false) {
        db.beginTransaction()
        try {
            db.execSQL("ALTER TABLE feeds ADD COLUMN serverId TEXT")
            db.execSQL("ALTER TABLE feeds ADD COLUMN serverVersion INTEGER")
            db.execSQL("ALTER TABLE feeds ADD COLUMN mutationRevision INTEGER NOT NULL DEFAULT 0")
            if (failAfterAlter) throw IllegalStateException("synthetic migration failure")
            db.execSQL("""CREATE TABLE feed_mutations (
                opId TEXT NOT NULL PRIMARY KEY, serverKey TEXT NOT NULL, url TEXT NOT NULL,
                kind TEXT NOT NULL, baseVersion INTEGER, fieldsJson TEXT NOT NULL,
                localRevision INTEGER NOT NULL, state TEXT NOT NULL, serverSnapshotJson TEXT,
                createdAt INTEGER NOT NULL, sequence INTEGER NOT NULL, sent INTEGER NOT NULL DEFAULT 0
            )""".trimIndent())
            db.execSQL("CREATE UNIQUE INDEX index_feed_mutations_serverKey_url_sequence ON feed_mutations(serverKey,url,sequence)")
            db.execSQL("""CREATE TABLE feed_sync_state (
                serverKey TEXT NOT NULL PRIMARY KEY, bindingUrl TEXT, configurationId TEXT,
                serverInstanceId TEXT, cursorVersion INTEGER, firstBindingComplete INTEGER NOT NULL DEFAULT 0,
                nextSequence INTEGER NOT NULL DEFAULT 1, lastOutcome TEXT, lastDiagnostic TEXT
            )""".trimIndent())
            var nextSequence = 1L
            db.rawQuery("SELECT url,name,mode,maxArticles,isEnabled FROM feeds WHERE url NOT LIKE 'synthetic://%' ORDER BY url", null).use { rows ->
                while (rows.moveToNext()) {
                    val proposal = JSONObject()
                        .put("title", rows.getString(1))
                        .put("mode", if (rows.getString(2) == "BRIEFING") "briefing" else "raw")
                        .put("max_articles", rows.getInt(3))
                        .put("is_active", rows.getInt(4) != 0)
                    db.execSQL("""INSERT INTO feed_mutations
                        (opId,serverKey,url,kind,baseVersion,fieldsJson,localRevision,state,
                         serverSnapshotJson,createdAt,sequence,sent)
                        VALUES (?,?,?,?,NULL,?,0,'legacy_unresolved',NULL,0,?,0)
                    """.trimIndent(), arrayOf("legacy-$nextSequence", "unbound", rows.getString(0), "upsert", proposal.toString(), nextSequence))
                    nextSequence++
                }
            }
            db.execSQL("INSERT INTO feed_sync_state (serverKey,nextSequence) VALUES ('unbound',?)", arrayOf(nextSequence))
            db.version = 9
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }
}
