package com.example.epilogue.data.local

import androidx.room.Room
import com.example.epilogue.data.repository.AndroidFeedV2Store
import com.example.epilogue.data.repository.FeedCorrectionEdits
import com.example.epilogue.data.repository.FeedRepository
import com.example.epilogue.data.repository.SettingsRepository
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.ui.feed.correctionDraft
import com.example.epilogue.ui.feed.correctionForm
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.sync.FeedV2Binding
import com.example.epilogue.shared.sync.FeedV2StoreResult
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.FeedSyncV2UseCase
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], manifest = Config.NONE, application = android.app.Application::class)
class AndroidFeedV2StoreTest {
    @get:Rule val files = TemporaryFolder()
    private val context get() = RuntimeEnvironment.getApplication()
    private val name get() = "feed-v2-${files.root.name}.db"
    private val serverId = "11111111-1111-4111-8111-111111111111"
    private val feedId = "22222222-2222-4222-8222-222222222222"
    private val url = "https://example.org/feed"
    private var configured = false
    private var destination = "https://one.invalid"
    private val settings = mockk<SettingsRepository> {
        every { isGhostwriterConfigured() } answers { configured }
        every { getGhostwriterUrl() } answers { destination }
    }
    private fun db() = Room.databaseBuilder(context, EpilogueDatabase::class.java, name)
        .allowMainThreadQueries().build()
    private fun feed(title: String = "Local") = Feed(url, title, ProcessingMode.FIDELITY, maxArticles = 0)
    private fun remote(title: String, version: Long = 1) = FeedSnapshotV2(
        "feed", feedId, url, version, title, true, "raw", 0
    )
    private fun <T> value(result: FeedV2StoreResult<T>): T = (result as FeedV2StoreResult.Success).value
    private suspend fun bind(store: AndroidFeedV2Store, changes: List<FeedSnapshotV2> = emptyList(),
        version: Long = changes.lastOrNull()?.version ?: 0): Pair<com.example.epilogue.shared.sync.FeedV2RunToken, FeedV2Binding> {
        val destination = store.currentDestination()!!
        val token = value(store.beginSyncRun(destination))
        val binding = value(store.reconcileAndBindFullSnapshot(token, destination,
            FeedChangesV2Response(serverId, version, changes)))
        return token to binding
    }

    @Test fun `new local URL requires host and port but keeps valid raw identity`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        for (invalid in listOf("http://:8080/rss", "http://example.org:bad/rss",
            "http://example.org:65536/rss")) {
            assertTrue(runCatching { store.saveLocal(feed("New").copy(url = invalid)) }.isFailure)
            assertNull(database.feedDao().getFeedByUrl(invalid))
            assertTrue(database.feedMutationDao().forUrl(invalid).isEmpty())
        }
        val raw = "HTTPS://[2001:DB8::1]:8080/Case/%2f?x=1%2F2"
        store.saveLocal(feed("Raw").copy(url = raw))
        assertEquals(raw, database.feedDao().getFeedByUrl(raw)!!.url)
        assertEquals(raw, database.feedMutationDao().forUrl(raw).single().url)
        database.close()
    }

    @Test fun `persisted legacy URL remains editable without changing its queued key`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val legacy = "http://:8080/rss"
        database.feedDao().insertFeed(FeedEntity(legacy, "Known", ProcessingMode.FIDELITY))
        store.saveLocal(feed("Edited").copy(url = legacy))
        assertEquals("Edited", database.feedDao().getFeedByUrl(legacy)!!.name)
        assertEquals(legacy, database.feedMutationDao().forUrl(legacy).single().url)
        database.close()
    }

    @Test fun `offline edit and delete retain ordered intents across Room restart`() = runBlocking {
        context.deleteDatabase(name)
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed())
        store.deleteLocal(url)
        assertTrue(database.feedDao().getAllFeedsList().isEmpty())
        assertEquals(listOf("upsert", "delete"), database.feedMutationDao().forUrl(url).map { it.kind })
        val firstId = database.feedMutationDao().forUrl(url).first().opId
        database.close()
        database = db()
        store = AndroidFeedV2Store(database, settings)
        assertTrue(database.feedDao().getAllFeedsList().isEmpty())
        assertEquals(firstId, database.feedMutationDao().forUrl(url).first().opId)
        assertEquals(3L, database.feedSyncStateDao().byKey("unbound")!!.nextSequence)
        database.close()
    }

    @Test fun `disabled Ghostwriter leaves migrated legacy feed available locally across restart`() = runBlocking {
        context.deleteDatabase(name)
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Legacy local"))
        val proposal = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(proposal.copy(state = "legacy_unresolved"))
        configured = true
        val scope = store.currentDestination()!!.configurationId
        assertTrue(database.feedDao().getEnabledFeedsList().isEmpty())
        configured = false
        assertEquals("Legacy local", FeedRepository(database.feedDao(), store, settings)
            .getEnabledFeedsList().single().name)
        assertEquals("legacy_unresolved", database.feedMutationDao().forScope(scope).single().state)
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, settings)
        assertEquals("Legacy local", FeedRepository(database.feedDao(), store, settings)
            .getEnabledFeedsList().single().name)
        assertEquals(proposal.opId, database.feedMutationDao().forScope(scope).single().opId)
        configured = true
        assertTrue(FeedRepository(database.feedDao(), store, settings).getEnabledFeedsList().isEmpty())
        database.close()
    }

    @Test fun `disabled generation includes hidden absent upsert after full bind and Room reopen`() = runBlocking {
        context.deleteDatabase(name)
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Offline proposal"))
        val head = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(head.copy(state = "legacy_unresolved"))
        configured = true
        val (token, _) = bind(store, emptyList())
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        assertEquals("needs_resolution", database.feedMutationDao().forUrl(url).single().state)
        assertTrue(FeedRepository(database.feedDao(), store, settings).getEnabledFeedsList().isEmpty())
        store.endSyncRun(token)
        configured = false
        assertEquals("Offline proposal", FeedRepository(database.feedDao(), store, settings)
            .getEnabledFeedsList().single().name)
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, settings)
        assertEquals("Offline proposal", FeedRepository(database.feedDao(), store, settings)
            .getEnabledFeedsList().single().name)
        assertEquals(head.opId, database.feedMutationDao().forUrl(url).first().opId)
        database.close()
    }

    @Test fun `disabled generation keeps a later local delete hidden after absent bind`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Local"))
        val head = database.feedMutationDao().forUrl(url).first()
        database.feedMutationDao().update(head.copy(state = "legacy_unresolved"))
        store.deleteLocal(url)
        configured = true
        val (token, _) = bind(store, emptyList())
        store.endSyncRun(token)
        assertEquals(listOf("upsert", "delete"), database.feedMutationDao().forUrl(url).map { it.kind })
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        configured = false
        assertTrue(FeedRepository(database.feedDao(), store, settings).getEnabledFeedsList().isEmpty())
        database.close()
    }

    @Test fun `full snapshot keeps mismatch and absence explicit including legacy dirty false`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Old"))
        // Simulate a migrated legacy proposal, whose old dirty flag was false.
        val old = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(old.copy(state = "legacy_unresolved"))
        database.feedDao().insertFeed(database.feedDao().getFeedByUrl(url)!!.copy(locallyModified = false))
        configured = true
        val (token, binding) = bind(store, listOf(remote("Server", 5)), 5)
        assertEquals(5L, binding.cursorVersion)
        assertEquals("Server", database.feedDao().getFeedByUrl(url)!!.name)
        assertEquals("needs_resolution", database.feedMutationDao().forUrl(url).single().state)
        assertTrue(database.feedMutationDao().forUrl(url).single().fieldsJson.contains("Old"))
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `sent payload replays identically and successor waits for exact acknowledgement`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("First"))
        val first = value(store.loadPendingMutations(token, binding, 100)).single()
        store.saveLocal(feed("Second"))
        val replay = value(store.loadPendingMutations(token, binding, 100)).single()
        assertEquals(first.opId, replay.opId)
        assertEquals(first.payload, replay.payload)
        assertEquals(first.sentRevision, replay.sentRevision)
        assertEquals(2, database.feedMutationDao().forUrl(url).size)
        assertTrue(store.acknowledge(token, binding, first.opId, first.sentRevision,
            remote("First", 1)) is FeedV2StoreResult.Success)
        val successor = value(store.loadPendingMutations(token, binding, 100)).single()
        assertNotEquals(first.opId, successor.opId)
        assertEquals(1L, successor.payload.baseVersion)
        assertEquals("Second", successor.payload.fields!!.title)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `newer pull leaves sent head replayable and older conflict keeps newer snapshot`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("Mine"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        assertTrue(store.applyServerChangesAndCursor(token, binding,
            FeedChangesV2Response(serverId, 5, listOf(remote("Web", 5)))) is FeedV2StoreResult.Success)
        assertEquals(sent.opId, value(store.loadPendingMutations(token, binding, 100)).single().opId)
        assertTrue(store.recordConflict(token, binding, sent.opId, sent.sentRevision,
            remote("Stale", 4)) is FeedV2StoreResult.Success)
        assertEquals(5L, database.feedDao().getFeedByUrl(url)!!.serverVersion)
        assertTrue(database.feedMutationDao().byId(sent.opId)!!.serverSnapshotJson!!.contains("Web"))
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `newer pull refreshes conflict before keep server or apply mine`() = runBlocking {
        for (action in listOf("keep_server", "apply_mine")) {
            context.deleteDatabase(name)
            configured = true
            val database = db()
            val store = AndroidFeedV2Store(database, settings)
            val (token, binding) = bind(store, listOf(remote("Original", 4)), 4)
            store.saveLocal(feed("Mine"))
            val sent = value(store.loadPendingMutations(token, binding, 100)).single()
            value(store.recordConflict(token, binding, sent.opId, sent.sentRevision, remote("Web 5", 5)))
            value(store.applyServerChangesAndCursor(token, binding,
                FeedChangesV2Response(serverId, 6, listOf(remote("Web 6", 6)))))
            assertTrue(database.feedMutationDao().byId(sent.opId)!!.serverSnapshotJson!!.contains("Web 6"))
            assertTrue(store.resolve(sent.opId, action))
            if (action == "keep_server") {
                assertEquals("Web 6", database.feedDao().getFeedByUrl(url)!!.name)
                assertEquals(6L, database.feedDao().getFeedByUrl(url)!!.serverVersion)
            } else {
                val replacement = value(store.loadPendingMutations(token, binding, 100)).single()
                assertEquals(6L, replacement.payload.baseVersion)
                assertEquals("Mine", replacement.payload.fields!!.title)
            }
            store.endSyncRun(token)
            database.close()
        }
    }

    @Test fun `conflict and keep server on earlier upsert cannot expose later delete`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store, listOf(remote("Original", 1)), 1)
        store.saveLocal(feed("Mine"))
        store.deleteLocal(url)
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        assertTrue(store.recordConflict(token, binding, sent.opId, sent.sentRevision,
            remote("Web", 2)) is FeedV2StoreResult.Success)
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        assertTrue(store.resolve(sent.opId, "keep_server"))
        assertEquals("Web", database.feedDao().getFeedByUrl(url)!!.name)
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        assertEquals(listOf("delete"), database.feedMutationDao().forUrl(url).map { it.kind })
        assertTrue(database.feedDao().getEnabledLocalFeedsList().isEmpty())
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `correcting rejected earlier upsert retains later delete despite newer sequence`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store, listOf(remote("Original", 1)), 1)
        store.saveLocal(feed("Invalid"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.deleteLocal(url)
        assertTrue(store.recordRejection(token, binding, sent.opId, sent.sentRevision,
            "invalid_fields", "Title invalid") is FeedV2StoreResult.Success)
        assertTrue(store.correctRejected(sent.opId, "Corrected", ProcessingMode.FIDELITY, true, 0))
        val rows = database.feedMutationDao().forUrl(url).sortedBy { it.queueOrder }
        assertEquals(listOf("upsert", "delete"), rows.map { it.kind })
        assertTrue(rows.first().sequence > rows.last().sequence)
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        assertTrue(database.feedDao().getAllFeedsList().isEmpty())
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `initial match to legacy proposal rebases later edit`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Legacy"))
        val legacy = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(legacy.copy(state = "legacy_unresolved"))
        store.saveLocal(feed("Edited"))
        configured = true
        val (token, binding) = bind(store, listOf(remote("Legacy", 5)), 5)
        assertNull(database.feedMutationDao().byId(legacy.opId))
        val successor = database.feedMutationDao().forUrl(url).single()
        assertEquals("queued", successor.state)
        assertEquals(5L, successor.baseVersion)
        assertEquals("Edited", database.feedDao().getFeedByUrl(url)!!.name)
        assertEquals(5L, value(store.loadPendingMutations(token, binding, 100)).single().payload.baseVersion)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `initial match to successor does not send null base create`() = runBlocking {
        context.deleteDatabase(name)
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        store.saveLocal(feed("Legacy"))
        val legacy = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(legacy.copy(state = "legacy_unresolved"))
        store.saveLocal(feed("Edited"))
        configured = true
        val (token, binding) = bind(store, listOf(remote("Edited", 5)), 5)
        assertEquals("needs_resolution", database.feedMutationDao().byId(legacy.opId)!!.state)
        assertTrue(value(store.loadPendingMutations(token, binding, 100)).isEmpty())
        assertTrue(store.resolve(legacy.opId, "keep_server"))
        assertTrue(value(store.loadPendingMutations(token, binding, 100)).isEmpty())
        assertEquals("needs_resolution", database.feedMutationDao().forUrl(url).single().state)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `suspension remains visible and destination switch invalidates old run`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        assertTrue(store.suspendBinding(token, binding, "changed_instance") is FeedV2StoreResult.Success)
        store.endSyncRun(token)
        assertEquals(binding.destination, store.currentDestination())
        val retry = value(store.beginSyncRun(binding.destination))
        assertTrue(value(store.getServerIdentity(retry))!!.suspended)
        store.endSyncRun(retry)
        destination = "https://two.invalid"
        assertEquals(binding.destination, store.currentDestination())
        assertTrue(store.prepareServerReconciliation())
        val next = store.currentDestination()!!
        assertNotEquals(binding.destination.configurationId, next.configurationId)
        assertTrue(database.feedSyncStateDao().byKey(binding.destination.configurationId)!!.suspended)
        database.close()
    }

    @Test fun `conflict replacement takes head slot while successor remains blocked`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("First"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.saveLocal(feed("Second"))
        assertTrue(store.recordConflict(token, binding, sent.opId, sent.sentRevision,
            remote("Server", 5)) is FeedV2StoreResult.Success)
        assertTrue(store.resolve(sent.opId, "apply_mine"))
        val replacement = value(store.loadPendingMutations(token, binding, 100)).single()
        assertNotEquals(sent.opId, replacement.opId)
        assertEquals(5L, replacement.payload.baseVersion)
        assertTrue(store.acknowledge(token, binding, replacement.opId, replacement.sentRevision,
            remote("First", 6)) is FeedV2StoreResult.Success)
        assertTrue(value(store.loadPendingMutations(token, binding, 100)).isEmpty())
        assertEquals("needs_resolution", database.feedMutationDao().forUrl(url).single().state)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `sent operation replays with same identity after database restart`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("Pending"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.endSyncRun(token)
        database.close()
        database = db()
        store = AndroidFeedV2Store(database, settings)
        val destination = store.currentDestination()!!
        val resumed = value(store.beginSyncRun(destination))
        val resumedBinding = value(store.getServerIdentity(resumed))!!
        val replay = value(store.loadPendingMutations(resumed, resumedBinding, 100)).single()
        assertEquals(sent.opId, replay.opId)
        assertEquals(sent.payload, replay.payload)
        assertEquals(sent.sentRevision, replay.sentRevision)
        store.endSyncRun(resumed)
        database.close()
    }

    @Test fun `delete then readd waits for tombstone acknowledgement and keeps server ID`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store, listOf(remote("Server", 7)), 7)
        store.deleteLocal(url)
        store.saveLocal(feed("Readded"))
        val deleted = value(store.loadPendingMutations(token, binding, 100)).single()
        assertEquals("delete", deleted.payload.kind)
        assertEquals(7L, deleted.payload.baseVersion)
        assertEquals(deleted.opId, value(store.loadPendingMutations(token, binding, 100)).single().opId)
        val tombstone = FeedSnapshotV2("tombstone", feedId, url, 8)
        assertTrue(store.acknowledge(token, binding, deleted.opId, deleted.sentRevision,
            tombstone) is FeedV2StoreResult.Success)
        val readd = value(store.loadPendingMutations(token, binding, 100)).single()
        assertEquals("upsert", readd.payload.kind)
        assertEquals(8L, readd.payload.baseVersion)
        assertEquals(feedId, database.feedDao().getFeedByUrl(url)!!.serverId)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `failed pull apply rolls back feed and cursor after restart`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        database.openHelper.writableDatabase.execSQL("""CREATE TRIGGER fail_feed_insert
            BEFORE INSERT ON feeds BEGIN SELECT RAISE(ABORT, 'synthetic feed apply failure'); END
        """.trimIndent())
        assertTrue(store.applyServerChangesAndCursor(token, binding,
            FeedChangesV2Response(serverId, 1, listOf(remote("Remote", 1)))) is FeedV2StoreResult.Failure)
        assertNull(database.feedDao().getFeedByUrl(url))
        assertEquals(0L, database.feedSyncStateDao().active()!!.cursorVersion)
        store.endSyncRun(token)
        database.close()
        database = db()
        store = AndroidFeedV2Store(database, settings)
        assertEquals(0L, database.feedSyncStateDao().active()!!.cursorVersion)
        assertNull(database.feedDao().getFeedByUrl(url))
        database.close()
    }

    @Test fun `rejection correction and discard preserve dependent successor`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("Invalid"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.saveLocal(feed("Later"))
        assertTrue(store.recordRejection(token, binding, sent.opId, sent.sentRevision,
            "invalid_fields", "Title invalid") is FeedV2StoreResult.Success)
        assertTrue(value(store.loadPendingMutations(token, binding, 100)).isEmpty())
        assertTrue(store.correctRejected(sent.opId, "Corrected", ProcessingMode.FIDELITY, true, 0))
        val corrected = value(store.loadPendingMutations(token, binding, 100)).single()
        assertNotEquals(sent.opId, corrected.opId)
        assertEquals("Corrected", corrected.payload.fields!!.title)
        assertTrue(store.acknowledge(token, binding, corrected.opId, corrected.sentRevision,
            remote("Corrected", 1)) is FeedV2StoreResult.Success)
        val successor = database.feedMutationDao().forUrl(url).single()
        assertEquals("needs_resolution", successor.state)
        assertTrue(store.resolve(successor.opId, "discard"))
        assertTrue(database.feedMutationDao().forUrl(url).isEmpty())
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `sparse rejected title correction excludes later disable after Room reopen`() = runBlocking {
        context.deleteDatabase(name)
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        configured = true
        val (token, binding) = bind(store, listOf(remote("Server", 5)), 5)
        store.saveLocal(feed("Invalid"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.saveLocal(feed("Invalid").copy(isEnabled = false))
        val successorId = database.feedMutationDao().forUrl(url).single { it.opId != sent.opId }.opId
        assertTrue(store.recordRejection(token, binding, sent.opId, sent.sentRevision,
            "invalid_fields", "Title invalid") is FeedV2StoreResult.Success)
        val head = database.feedMutationDao().byId(sent.opId)!!
        assertTrue(head.fieldsJson.contains("Invalid"))
        assertFalse(head.fieldsJson.contains("is_active"))
        assertTrue(head.serverSnapshotJson!!.contains("Server"))
        assertFalse(database.feedDao().getFeedByUrl(url)!!.isEnabled)
        store.endSyncRun(token)
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, settings)
        val draft = requireNotNull(correctionDraft(database.feedMutationDao().byId(sent.opId)!!))
        assertEquals("Invalid", draft.title)
        assertTrue(draft.enabled) // the head's server state, not the queued disable
        assertTrue(store.correctRejected(sent.opId, "Corrected", draft.mode,
            draft.enabled, draft.maxArticles))
        val successor = database.feedMutationDao().byId(successorId)!!
        assertEquals("needs_resolution", successor.state)
        assertTrue(store.resolve(successor.opId, "discard").not()) // head still owns the URL
        val destination = store.currentDestination()!!
        val nextToken = value(store.beginSyncRun(destination))
        val nextBinding = value(store.getServerIdentity(nextToken))!!
        val corrected = value(store.loadPendingMutations(nextToken, nextBinding, 100)).single()
        assertEquals("Corrected", corrected.payload.fields!!.title)
        assertEquals(true, corrected.payload.fields!!.isActive)
        assertTrue(store.acknowledge(nextToken, nextBinding, corrected.opId, corrected.sentRevision,
            remote("Corrected", 6)) is FeedV2StoreResult.Success)
        assertTrue(store.resolve(successor.opId, "discard"))
        assertTrue(database.feedDao().getFeedByUrl(url)!!.isEnabled)
        store.endSyncRun(nextToken)
        database.close()
    }

    @Test fun `rejected title successor inherits acknowledged mode after Room reopen`() = runBlocking {
        context.deleteDatabase(name)
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        configured = true
        val (token, binding) = bind(store, listOf(remote("Server", 5)), 5)
        store.saveLocal(feed("Server").copy(mode = ProcessingMode.BRIEFING))
        val first = value(store.loadPendingMutations(token, binding, 100)).single()
        store.saveLocal(feed("Bad title").copy(mode = ProcessingMode.BRIEFING))
        val successor = database.feedMutationDao().forUrl(url).single { it.opId != first.opId }
        assertFalse(successor.fieldsJson.contains("mode"))
        val staleSnapshot = successor.serverSnapshotJson
        assertTrue(staleSnapshot!!.contains("\"raw\""))
        val acknowledged = remote("Server", 6).copy(mode = "summarize")
        assertTrue(store.acknowledge(token, binding, first.opId, first.sentRevision,
            acknowledged) is FeedV2StoreResult.Success)
        val rebased = database.feedMutationDao().byId(successor.opId)!!
        assertEquals(6L, rebased.baseVersion)
        assertTrue(rebased.serverSnapshotJson!!.contains("\"summarize\""))
        // A pre-fix queued row may already be persisted with the older snapshot.
        database.feedMutationDao().update(rebased.copy(serverSnapshotJson = staleSnapshot))
        store.endSyncRun(token)
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, settings)
        val nextToken = value(store.beginSyncRun(store.currentDestination()!!))
        val nextBinding = value(store.getServerIdentity(nextToken))!!
        val sent = value(store.loadPendingMutations(nextToken, nextBinding, 100)).single()
        assertEquals(successor.opId, sent.opId)
        assertTrue(store.recordRejection(nextToken, nextBinding, sent.opId, sent.sentRevision,
            "invalid_fields", "Title invalid") is FeedV2StoreResult.Success)
        val rejected = database.feedMutationDao().byId(sent.opId)!!
        assertTrue(rejected.serverSnapshotJson!!.contains("\"summarize\""))
        val draft = requireNotNull(correctionDraft(rejected))
        assertEquals(ProcessingMode.BRIEFING, draft.mode)
        assertTrue(store.correctRejected(sent.opId, "Corrected", draft.mode,
            draft.enabled, draft.maxArticles))
        val corrected = value(store.loadPendingMutations(nextToken, nextBinding, 100)).single()
        assertEquals("summarize", corrected.payload.fields!!.mode)
        assertTrue(store.acknowledge(nextToken, nextBinding, corrected.opId, corrected.sentRevision,
            remote("Corrected", 7).copy(mode = "summarize")) is FeedV2StoreResult.Success)
        assertEquals(ProcessingMode.BRIEFING, database.feedDao().getFeedByUrl(url)!!.mode)
        store.endSyncRun(nextToken)
        database.close()
    }

    @Test fun `open title correction submits refreshed server defaults`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store, listOf(remote("Server", 5)), 5)
        store.saveLocal(feed("Rejected"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        assertTrue(store.recordRejection(token, binding, sent.opId, sent.sentRevision,
            "invalid_fields", "Title invalid") is FeedV2StoreResult.Success)
        val initial = requireNotNull(correctionDraft(database.feedMutationDao().byId(sent.opId)!!))
        assertEquals(ProcessingMode.FIDELITY, initial.mode)
        assertTrue(initial.enabled)

        val remoteChanged = remote("Server", 6).copy(mode = "summarize", isActive = false,
            maxArticles = 7)
        assertTrue(store.applyServerChangesAndCursor(token, binding,
            FeedChangesV2Response(serverId, 6, listOf(remoteChanged))) is FeedV2StoreResult.Success)
        val refreshed = requireNotNull(correctionDraft(database.feedMutationDao().byId(sent.opId)!!))
        val form = correctionForm(refreshed, "Corrected", null, null, null)
        assertEquals(ProcessingMode.BRIEFING, form.mode)
        assertFalse(form.enabled)
        assertEquals("7", form.cap)
        // The UI captured only the title edit before its required pre-submit sync.
        // Room resolves untouched fields after that pull, in the write transaction.
        assertTrue(store.correctRejected(sent.opId, FeedCorrectionEdits(title = "Corrected")))
        val corrected = value(store.loadPendingMutations(token, binding, 100)).single()
        assertEquals(6L, corrected.payload.baseVersion)
        assertEquals("Corrected", corrected.payload.fields!!.title)
        assertEquals("summarize", corrected.payload.fields!!.mode)
        assertEquals(false, corrected.payload.fields!!.isActive)
        assertEquals(7, corrected.payload.fields!!.maxArticles)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `only per URL head is actionable and direct successor resolution is rejected after reopen`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        var database = db()
        var store = AndroidFeedV2Store(database, settings)
        bind(store)
        store.saveLocal(feed("First"))
        val first = database.feedMutationDao().forUrl(url).single()
        database.feedMutationDao().update(first.copy(state = "needs_resolution"))
        val second = first.copy(opId = UUID.randomUUID().toString(), state = "rejected",
            sequence = first.sequence + 1, queueOrder = first.queueOrder + 1,
            fieldsJson = """{"title":"Second"}""")
        val third = second.copy(opId = UUID.randomUUID().toString(),
            sequence = second.sequence + 1, queueOrder = second.queueOrder + 1,
            fieldsJson = """{"title":"Third"}""")
        database.feedMutationDao().insert(second)
        database.feedMutationDao().insert(third)
        assertEquals(listOf(first.opId), database.feedMutationDao().unresolvedFlow().first().map { it.opId })
        database.close()

        database = db()
        store = AndroidFeedV2Store(database, settings)
        assertFalse(store.resolve(third.opId, "discard"))
        assertFalse(store.correctRejected(third.opId, "Third", ProcessingMode.FIDELITY, true, 0))
        assertTrue(store.resolve(first.opId, "keep_server"))
        assertEquals(listOf(second.opId), database.feedMutationDao().unresolvedFlow().first().map { it.opId })
        assertFalse(store.resolve(third.opId, "discard"))
        assertTrue(store.resolve(second.opId, "discard"))
        assertEquals(listOf(third.opId), database.feedMutationDao().unresolvedFlow().first().map { it.opId })
        database.close()
    }

    @Test fun `settings switch makes old token unable to commit after network response`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store)
        store.saveLocal(feed("Pending"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        store.beforeDestinationChange("https://two.invalid")
        destination = "https://two.invalid"
        val staleUseCase = mockk<FeedSyncV2UseCase>()
        coEvery { staleUseCase.sync() } returns FeedSyncV2Outcome.Failed("pull", "stale binding")
        store.syncAndRecord(staleUseCase)
        assertEquals(binding.destination, store.currentDestination())
        assertTrue(database.feedSyncStateDao().active()!!.suspended)
        assertEquals("server_changed", database.feedSyncStateDao().active()!!.lastOutcome)
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.acknowledge(token, binding, sent.opId, sent.sentRevision, remote("Pending", 1)))
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.applyServerChangesAndCursor(token, binding, FeedChangesV2Response(serverId, 1, listOf(remote("Remote", 1)))))
        assertNotNull(database.feedMutationDao().byId(sent.opId))
        assertEquals(0L, database.feedSyncStateDao().byKey(binding.destination.configurationId)!!.cursorVersion)
        store.endSyncRun(token)
        database.close()
    }

    @Test fun `changed server requires explicit reconciliation with new IDs and no old replay`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (token, binding) = bind(store, listOf(remote("Server", 4)), 4)
        store.saveLocal(feed("Mine"))
        val sent = value(store.loadPendingMutations(token, binding, 100)).single()
        assertTrue(store.suspendBinding(token, binding, "changed_instance") is FeedV2StoreResult.Success)
        store.endSyncRun(token)
        assertEquals(binding.destination, store.currentDestination())
        assertTrue(store.prepareServerReconciliation())
        val replacementDestination = store.currentDestination()!!
        assertNotEquals(binding.destination.configurationId, replacementDestination.configurationId)
        assertNotNull(database.feedMutationDao().byId(sent.opId))
        val copied = database.feedMutationDao().forScope(replacementDestination.configurationId).single()
        assertNotEquals(sent.opId, copied.opId)
        assertFalse(copied.sent)
        assertEquals("needs_resolution", copied.state)
        val retryToken = value(store.beginSyncRun(replacementDestination))
        val rebound = value(store.reconcileAndBindFullSnapshot(retryToken, replacementDestination,
            com.example.epilogue.shared.ghostwriter.FeedChangesV2Response(
                "33333333-3333-4333-8333-333333333333", 1,
                listOf(remote("New server", 1)))))
        assertTrue(value(store.loadPendingMutations(retryToken, rebound, 100)).isEmpty())
        assertEquals("needs_resolution", database.feedMutationDao().byId(copied.opId)!!.state)
        store.endSyncRun(retryToken)
        database.close()
    }

    @Test fun `destination switch retains old proposal and hides absent cached feed until explicit choice`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (oldToken, oldBinding) = bind(store, listOf(remote("Server A", 4)), 4)
        store.saveLocal(feed("Mine on A"))
        val oldOp = database.feedMutationDao().forScope(oldBinding.destination.configurationId).single()
        store.beforeDestinationChange("https://two.invalid")
        destination = "https://two.invalid"
        assertEquals(oldBinding.destination, store.currentDestination())
        assertEquals("server_changed", database.feedSyncStateDao().active()!!.lastOutcome)
        assertEquals(FeedV2StoreResult.StaleBinding,
            store.applyServerChangesAndCursor(oldToken, oldBinding,
                FeedChangesV2Response(serverId, 5, emptyList())))
        store.endSyncRun(oldToken)
        assertTrue(store.prepareServerReconciliation())
        val newDestination = store.currentDestination()!!
        assertEquals("https://two.invalid", newDestination.normalizedBaseUrl)
        val newToken = value(store.beginSyncRun(newDestination))
        val newBinding = value(store.reconcileAndBindFullSnapshot(newToken, newDestination,
            FeedChangesV2Response("44444444-4444-4444-8444-444444444444", 0, emptyList())))
        assertTrue(value(store.loadPendingMutations(newToken, newBinding, 100)).isEmpty())
        val copied = database.feedMutationDao().forScope(newDestination.configurationId).single()
        assertNotEquals(oldOp.opId, copied.opId)
        assertEquals("needs_resolution", copied.state)
        assertTrue(copied.fieldsJson.contains("Mine on A"))
        assertTrue(database.feedDao().getFeedByUrl(url)!!.hiddenDelete)
        assertTrue(database.feedDao().getEnabledFeedsList().isEmpty())
        assertNotNull(database.feedMutationDao().byId(oldOp.opId))
        store.endSyncRun(newToken)
        assertTrue(store.resolve(copied.opId, "add_to_server"))
        assertEquals("queued", database.feedMutationDao().forScope(newDestination.configurationId).single().state)
        val replayToken = value(store.beginSyncRun(newDestination))
        val add = value(store.loadPendingMutations(replayToken, newBinding, 100)).single().payload
        assertNull(add.baseVersion)
        assertTrue(add.fields!!.isComplete())
        assertEquals("Mine on A", add.fields!!.title)
        store.endSyncRun(replayToken)
        database.close()
    }

    @Test fun `old scope legacy unresolved does not block new scope reconciled feed generation`() = runBlocking {
        context.deleteDatabase(name)
        configured = true
        val database = db()
        val store = AndroidFeedV2Store(database, settings)
        val (oldToken, oldBinding) = bind(store, listOf(remote("Server A", 4)), 4)
        store.saveLocal(feed("My title"))
        val old = database.feedMutationDao().forScope(oldBinding.destination.configurationId).single()
        database.feedMutationDao().update(old.copy(state = "legacy_unresolved"))
        store.beforeDestinationChange("https://two.invalid")
        destination = "https://two.invalid"
        store.endSyncRun(oldToken)
        assertTrue(store.prepareServerReconciliation())
        val next = store.currentDestination()!!
        val token = value(store.beginSyncRun(next))
        value(store.reconcileAndBindFullSnapshot(token, next,
            FeedChangesV2Response("44444444-4444-4444-8444-444444444444", 1,
                listOf(remote("Server B", 1)))))
        store.endSyncRun(token)
        val newProposal = database.feedMutationDao().forScope(next.configurationId).single()
        assertTrue(store.resolve(newProposal.opId, "keep_server"))
        assertEquals("Server B", database.feedDao().getEnabledFeedsList().single().name)
        assertEquals("legacy_unresolved", database.feedMutationDao().byId(old.opId)!!.state)
        database.close()
    }
}
