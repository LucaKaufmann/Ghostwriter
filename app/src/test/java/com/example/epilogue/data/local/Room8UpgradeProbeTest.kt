package com.example.epilogue.data.local

import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteConstraintException
import androidx.room.Room
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.domain.model.TriggerType
import kotlinx.coroutines.runBlocking
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

/** An isolated feasibility probe. Production Room remains at version 8. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class Room8UpgradeProbeTest {
    @get:Rule val files = TemporaryFolder()

    private val context get() = RuntimeEnvironment.getApplication()
    private val name get() = "room-8-probe-${files.root.name}.db"
    private val path get() = context.getDatabasePath(name)
    private lateinit var artifact: File

    private fun room8(): EpilogueDatabase =
        Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
            .allowMainThreadQueries()
            .build()

    private fun createFixture() = runBlocking {
        context.deleteDatabase(name)
        artifact = files.newFile("fixture.epub").apply { writeText("synthetic EPUB bytes") }
        val db = room8()
        db.feedDao().insertFeed(FeedEntity("https://example.org/unchanged", "Local title", ProcessingMode.FIDELITY,
            lastFetched = 1234L, maxArticles = 0, isEnabled = true, serverUpdatedAt = 77L, locallyModified = false))
        db.feedDao().insertFeed(FeedEntity("https://example.org/dirty", "Edited title", ProcessingMode.BRIEFING,
            lastFetched = 9876L, maxArticles = 4, isEnabled = false, serverUpdatedAt = 88L, locallyModified = true))
        db.feedDao().insertFeed(FeedEntity("synthetic://wallabag", "Wallabag", ProcessingMode.FIDELITY,
            lastFetched = 55L, locallyModified = true))
        val digestId = db.digestDao().insertDigest(DigestEntity(
            generatedAt = 100L, epubFilePath = artifact.absolutePath, articleCount = 1,
            briefingCount = 0, fidelityCount = 1, triggerType = TriggerType.MANUAL,
            feedNames = "Local title", remoteId = null, period = "manual", isComplete = true
        ))
        db.digestDao().insertArticles(listOf(DigestArticleEntity(
            digestId = digestId, title = "Kept article", author = "Author", content = "Synthetic content",
            originalUrl = "https://example.org/article", isSummary = false, feedName = "Local title", sortOrder = 0
        )))
        db.close()
    }

    private fun SQLiteDatabase.scalar(sql: String): String? = rawQuery(sql, null).use {
        if (it.moveToFirst() && !it.isNull(0)) it.getString(0) else null
    }

    @Test fun `real Room 8 file reopens with feeds and history intact`() = runBlocking {
        createFixture()
        assertTrue(path.isFile)
        val reopened = room8()
        assertEquals(8, reopened.openHelper.readableDatabase.version)
        assertEquals(3, reopened.feedDao().getAllFeedsList().size)
        assertEquals(1234L, reopened.feedDao().getFeedByUrl("https://example.org/unchanged")!!.lastFetched)
        assertFalse(reopened.feedDao().getFeedByUrl("https://example.org/unchanged")!!.locallyModified)
        assertTrue(reopened.feedDao().getFeedByUrl("https://example.org/dirty")!!.locallyModified)
        val digest = reopened.digestDao().getAllDigestsList().single()
        assertEquals(artifact.absolutePath, digest.epubFilePath)
        assertEquals("synthetic EPUB bytes", artifact.readText())
        assertEquals("Kept article", reopened.digestDao().getArticlesForDigest(digest.id).single().title)
        reopened.close()
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

    @Test fun `failed probe rolls back DDL and original Room 8 file reopens`() = runBlocking {
        createFixture()
        SQLiteDatabase.openDatabase(path.absolutePath, null, SQLiteDatabase.OPEN_READWRITE).use { db ->
            assertThrows(IllegalStateException::class.java) { probeMigration(db, failAfterAlter = true) }
            assertEquals(8, db.version)
            assertEquals("0", db.scalar("SELECT COUNT(*) FROM pragma_table_info('feeds') WHERE name='serverVersion'"))
            assertEquals("0", db.scalar("SELECT COUNT(*) FROM sqlite_master WHERE name='feed_mutations'"))
        }
        val reopened = room8()
        assertEquals(3, reopened.feedDao().getAllFeedsList().size)
        assertEquals("Edited title", reopened.feedDao().getFeedByUrl("https://example.org/dirty")!!.name)
        assertEquals(1, reopened.digestDao().getAllDigestsList().size)
        assertEquals("synthetic EPUB bytes", artifact.readText())
        reopened.close()
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
