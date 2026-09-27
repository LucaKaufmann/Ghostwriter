package com.example.epilogue.data.local

import android.content.Context
import androidx.room.Room
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import com.example.epilogue.shared.sync.FeedV2RemotePort
import com.example.epilogue.shared.sync.FeedV2StoreResult
import io.mockk.mockk
import io.mockk.mockkConstructor
import io.mockk.mockkStatic
import io.mockk.every
import io.mockk.unmockkConstructor
import io.mockk.unmockkStatic
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class AndroidFeedV2UrlRevertTest {
    @get:Rule val files = TemporaryFolder()
    private val context get() = RuntimeEnvironment.getApplication()
    private val name get() = "url-revert-${files.root.name}.db"
    private val a = "https://a.invalid"
    private val b = "https://b.invalid"
    private val feedUrl = "https://example.org/feed"

    private fun db() = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
        .allowMainThreadQueries().build()
    private fun <T> value(result: FeedV2StoreResult<T>): T =
        (result as FeedV2StoreResult.Success).value
    private fun feed() = Feed(feedUrl, "Local proposal", ProcessingMode.FIDELITY, maxArticles = 0)

    @Before fun clearPreferences() {
        context.getSharedPreferences("epilog_settings", Context.MODE_PRIVATE).edit().clear().commit()
        mockkConstructor(MasterKey.Builder::class)
        every { anyConstructed<MasterKey.Builder>().build() } returns mockk()
        mockkStatic(EncryptedSharedPreferences::class)
        every { EncryptedSharedPreferences.create(any<Context>(), any<String>(),
            any<MasterKey>(), any(), any()) } answers {
            context.getSharedPreferences("synthetic_secure_settings", Context.MODE_PRIVATE)
        }
        context.deleteDatabase(name)
    }

    @After fun clearDatabase() {
        context.deleteDatabase(name)
        unmockkStatic(EncryptedSharedPreferences::class)
        unmockkConstructor(MasterKey.Builder::class)
    }

    private suspend fun bind(store: AndroidFeedV2Store) =
        store.currentDestination()!!.let { destination ->
            val token = value(store.beginSyncRun(destination))
            val binding = value(store.reconcileAndBindFullSnapshot(token, destination,
                FeedChangesV2Response("11111111-1111-4111-8111-111111111111", 0, emptyList())))
            Triple(destination, token, binding)
        }

    @Test fun `transient A to B to A invalidates tokens without suspending or losing outbox across reopen`() = runBlocking {
        var database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        var store = AndroidFeedV2Store(database, settings)
        val (destination, oldToken, oldBinding) = bind(store)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()
        val oldGeneration = database.feedSyncStateDao().active()!!.generation
        val oldOutcome = database.feedSyncStateDao().active()!!.lastOutcome

        settings.setGhostwriterUrl(b)
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.loadPendingMutations(oldToken, oldBinding, 100))
        assertEquals(FeedV2StoreResult.StaleBinding, store.beginSyncRun(destination))
        store.recordOutcome(FeedSyncV2Outcome.Complete(0, 0))
        assertEquals(oldOutcome, database.feedSyncStateDao().active()!!.lastOutcome)
        settings.setGhostwriterUrl(a)
        assertEquals(oldGeneration + 2, database.feedSyncStateDao().active()!!.generation)
        assertFalse(database.feedSyncStateDao().active()!!.suspended)
        assertEquals(destination, store.currentDestination())
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.loadPendingMutations(oldToken, oldBinding, 100))
        store.endSyncRun(oldToken)
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, SettingsRepository(context, database))
        assertFalse(database.feedSyncStateDao().active()!!.suspended)
        assertEquals(proposal.opId, database.feedMutationDao().forScope(destination.configurationId).single().opId)
        val newToken = value(store.beginSyncRun(destination))
        val newBinding = value(store.getServerIdentity(newToken))!!
        assertEquals(oldGeneration + 2, newBinding.generation)
        assertEquals(proposal.opId, value(store.loadPendingMutations(newToken, newBinding, 100)).single().opId)
        store.endSyncRun(newToken)
        database.close()
    }

    @Test fun `saved URL guard rejects a token minted after generation bump but before preference publication`() = runBlocking {
        val database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        val store = AndroidFeedV2Store(database, settings)
        val (destination, oldToken, _) = bind(store)
        store.endSyncRun(oldToken)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()

        // Inject the two stages of setGhostwriterUrl separately: generation was
        // committed, but the saved preference still names A when this token starts.
        val state = database.feedSyncStateDao().active()!!
        database.feedSyncStateDao().put(state.copy(generation = state.generation + 1))
        val gapToken = value(store.beginSyncRun(destination))
        val gapBinding = value(store.getServerIdentity(gapToken))!!
        val gapGeneration = database.feedSyncStateDao().active()!!.generation
        context.getSharedPreferences("epilog_settings", Context.MODE_PRIVATE).edit()
            .putString("ghostwriter_url", b).commit()
        assertEquals(gapGeneration, database.feedSyncStateDao().active()!!.generation)
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.loadPendingMutations(gapToken, gapBinding, 100))
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.applyServerChangesAndCursor(gapToken, gapBinding,
                FeedChangesV2Response("11111111-1111-4111-8111-111111111111", 1, emptyList())))
        assertEquals(proposal.opId, database.feedMutationDao().forScope(destination.configurationId).single().opId)
        store.endSyncRun(gapToken)
        database.close()
    }

    @Test fun `real instance suspension survives URL roundtrip with diagnostic and outbox`() = runBlocking {
        val database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        val store = AndroidFeedV2Store(database, settings)
        val (destination, token, binding) = bind(store)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()
        assertTrue(store.suspendBinding(token, binding, "changed_instance") is FeedV2StoreResult.Success)
        store.endSyncRun(token)

        settings.setGhostwriterUrl(b)
        settings.setGhostwriterUrl(a)
        val state = database.feedSyncStateDao().active()!!
        assertTrue(state.suspended)
        assertEquals("server_changed", state.lastOutcome)
        assertEquals("changed_instance", state.lastDiagnostic)
        assertEquals(proposal.opId, database.feedMutationDao().forScope(destination.configurationId).single().opId)
        assertEquals(destination, store.currentDestination())
        database.close()
    }

    @Test fun `selected B suspends A and reports ServerChanged without remote requests`() = runBlocking {
        val database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        val store = AndroidFeedV2Store(database, settings)
        val (destination, token, _) = bind(store)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()
        store.endSyncRun(token)

        settings.setGhostwriterUrl(b)
        val remote = mockk<FeedV2RemotePort>()
        assertEquals(FeedSyncV2Outcome.ServerChanged, FeedSyncV2UseCase(store, store, remote).sync())
        assertTrue(database.feedSyncStateDao().active()!!.suspended)
        assertEquals("server_changed", database.feedSyncStateDao().active()!!.lastOutcome)
        settings.setGhostwriterUrl(a)
        assertTrue(database.feedSyncStateDao().active()!!.suspended)
        assertEquals(destination, store.currentDestination())
        assertEquals(proposal.opId, database.feedMutationDao().forScope(destination.configurationId).single().opId)
        database.close()
    }

    @Test fun `B configuration blocks local resolution but disabled A retains local correction`() = runBlocking {
        val database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        val store = AndroidFeedV2Store(database, settings)
        val (destination, token, _) = bind(store)
        store.endSyncRun(token)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()
        database.feedMutationDao().update(proposal.copy(state = "rejected"))

        settings.setGhostwriterUrl(b)
        assertFalse(store.resolve(proposal.opId, "discard"))
        assertFalse(store.correctRejected(proposal.opId, "Corrected", ProcessingMode.FIDELITY, true, 0))
        assertEquals("rejected", database.feedMutationDao().byId(proposal.opId)?.state)
        settings.setGhostwriterUrl(a)
        settings.setGhostwriterEnabled(false)
        assertTrue(store.correctRejected(proposal.opId, "Corrected", ProcessingMode.FIDELITY, true, 0))
        assertFalse(database.feedSyncStateDao().active()!!.suspended)
        database.close()
    }

    @Test fun `failed generation write keeps old URL and queued proposal`() = runBlocking {
        val database = db()
        val settings = SettingsRepository(context, database)
        settings.setGhostwriterEnabled(true)
        settings.setGhostwriterUrl(a)
        val store = AndroidFeedV2Store(database, settings)
        val (destination, token, _) = bind(store)
        store.endSyncRun(token)
        store.saveLocal(feed())
        val proposal = database.feedMutationDao().forScope(destination.configurationId).single()
        database.openHelper.writableDatabase.execSQL("""
            CREATE TRIGGER reject_state_write BEFORE INSERT ON feed_sync_state
            BEGIN SELECT RAISE(ABORT, 'synthetic state failure'); END
        """.trimIndent())
        var failed = false
        try { settings.setGhostwriterUrl(b) } catch (_: Exception) { failed = true }
        assertTrue(failed)
        assertEquals(a, settings.getGhostwriterUrl())
        assertEquals(proposal.opId, database.feedMutationDao().forScope(destination.configurationId).single().opId)
        database.openHelper.writableDatabase.execSQL("DROP TRIGGER reject_state_write")
        database.close()
    }
}
