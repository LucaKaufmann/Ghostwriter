package com.example.epilogue.data.local

import androidx.room.Room
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.ghostwriter.feedV2Json
import java.io.File
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/** Synthetic, production-schema database for inspecting the real conflict UI on an emulator. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class Room9UiFixtureTest {
    @Test fun `export production Room9 conflict fixture`() = runBlocking {
        val context = RuntimeEnvironment.getApplication()
        val name = "epilog_database"
        context.deleteDatabase(name)
        val database = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
            .allowMainThreadQueries().build()
        val key = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        database.feedSyncStateDao().put(FeedSyncStateEntity(
            serverKey = key, bindingUrl = "https://fixture.invalid",
            configurationId = key, serverInstanceId = "11111111-1111-4111-8111-111111111111",
            cursorVersion = 7, firstBindingComplete = true, nextSequence = 5,
            active = true, lastOutcome = "partial", lastDiagnostic = "Review four synthetic proposals"
        ))
        val definitions = listOf(
            Fixture("conflict", "Server headline", "My headline", "needs_resolution", "upsert", false, 5),
            Fixture("rejected", "Rejected draft", "Rejected draft", "rejected", "upsert", false, 6),
            Fixture("absent", "My absent feed", "My absent feed", "needs_resolution", "upsert", true, null),
            Fixture("hidden-delete", "Server restored feed", "Server restored feed", "needs_resolution", "delete", true, 7)
        )
        definitions.forEachIndexed { index, fixture ->
            val url = "https://fixture.invalid/feed/${fixture.slug}"
            val snapshot = fixture.serverVersion?.let { version -> feedV2Json.encodeToString(
                FeedSnapshotV2("feed", "22222222-2222-4222-8222-22222222222${index}",
                    url, version, fixture.serverTitle, true, "raw", 0)) }
            database.feedDao().insertFeed(FeedEntity(
                url = url, name = fixture.serverTitle, mode = ProcessingMode.FIDELITY,
                serverVersion = fixture.serverVersion, hiddenDelete = fixture.hidden,
                serverSnapshotJson = snapshot
            ))
            database.feedMutationDao().insert(FeedMutationEntity(
                opId = "33333333-3333-4333-8333-33333333333${index}", serverKey = key,
                url = url, kind = fixture.kind, baseVersion = fixture.serverVersion,
                fieldsJson = if (fixture.kind == "delete") "{}" else
                    """{"title":"${fixture.localTitle}","is_active":true,"mode":"raw","max_articles":0}""",
                localRevision = 1, state = fixture.state, serverSnapshotJson = snapshot,
                createdAt = 1_000L + index, sequence = index + 1L, queueOrder = index + 1L,
                rejectionCode = if (fixture.state == "rejected") "invalid_fields" else null,
                rejectionMessage = if (fixture.state == "rejected") "Synthetic title needs correction" else null
            ))
        }
        assertEquals(2, database.feedDao().getAllFeedsList().size)
        assertEquals(4, database.feedMutationDao().forScope(key).size)
        database.close()
        val source = context.getDatabasePath(name)
        val output = File(System.getProperty("epilogue.uiFixtureOutput") ?:
            File(System.getProperty("java.io.tmpdir"), "epilogue-room9-ui-fixture.db").path)
        source.copyTo(output, overwrite = true)
        assertTrue(output.length() > 0)
        val reopened = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
            .allowMainThreadQueries().build()
        assertEquals(4, reopened.feedMutationDao().forScope(key).size)
        reopened.close()
    }

    private data class Fixture(
        val slug: String, val serverTitle: String, val localTitle: String,
        val state: String, val kind: String, val hidden: Boolean, val serverVersion: Long?
    )
}
