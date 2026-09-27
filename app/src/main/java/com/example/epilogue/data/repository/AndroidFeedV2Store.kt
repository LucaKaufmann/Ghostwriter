package com.example.epilogue.data.repository

import androidx.room.withTransaction
import com.example.epilogue.data.local.EpilogueDatabase
import com.example.epilogue.data.local.FeedEntity
import com.example.epilogue.data.local.FeedMutationEntity
import com.example.epilogue.data.local.FeedSyncStateEntity
import com.example.epilogue.domain.model.Feed
import com.example.epilogue.domain.model.ProcessingMode
import com.example.epilogue.shared.ghostwriter.FeedChangesV2Response
import com.example.epilogue.shared.ghostwriter.FeedDirtyFieldsV2
import com.example.epilogue.shared.ghostwriter.FeedMutationV2
import com.example.epilogue.shared.ghostwriter.FeedSnapshotV2
import com.example.epilogue.shared.ghostwriter.feedV2Json
import com.example.epilogue.shared.ghostwriter.isFeedUrlV2
import com.example.epilogue.shared.sync.FeedV2Binding
import com.example.epilogue.shared.sync.FeedV2ConfigurationPort
import com.example.epilogue.shared.sync.FeedV2Destination
import com.example.epilogue.shared.sync.FeedV2RunToken
import com.example.epilogue.shared.sync.FeedV2StorePort
import com.example.epilogue.shared.sync.FeedV2StoreResult
import com.example.epilogue.shared.sync.FeedV2WorkSummary
import com.example.epilogue.shared.sync.FeedSyncV2Outcome
import com.example.epilogue.shared.sync.SentFeedMutationV2
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/** Owns the Room transactions behind the shared v2 state machine. */
@Singleton
class AndroidFeedV2Store @Inject constructor(
    private val database: EpilogueDatabase,
    private val settings: SettingsRepository
) : FeedV2StorePort, FeedV2ConfigurationPort {
    private val feeds get() = database.feedDao()
    private val mutations get() = database.feedMutationDao()
    private val states get() = database.feedSyncStateDao()
    private val gate = Any()
    private var activeToken: String? = null
    private var activeRun: Pair<FeedV2Destination, Long>? = null

    private fun normalizedUrl(url: String): String = url.trim().trimEnd('/').removeSuffix("/api")

    override suspend fun currentDestination(): FeedV2Destination? {
        if (!settings.isGhostwriterConfigured()) return null
        val url = settings.getGhostwriterUrl()?.let(::normalizedUrl)?.takeIf { it.isNotBlank() } ?: return null
        return database.withTransaction {
            val active = states.active()
            if (active != null) {
                if (active.bindingUrl != url && !active.suspended) {
                    states.put(active.copy(suspended = true, generation = active.generation + 1,
                        lastOutcome = "server_changed", lastDiagnostic = "Destination changed"))
                }
                // Keep the old scope visible until the user explicitly reviews the new server.
                FeedV2Destination(active.bindingUrl!!, active.configurationId!!)
            } else {
                val id = UUID.randomUUID().toString()
                val unbound = states.byKey("unbound")
                val hasUnboundIntents = unbound != null && mutations.forScope("unbound").isNotEmpty()
                states.put(FeedSyncStateEntity(
                    serverKey = id, bindingUrl = url, configurationId = id,
                    nextSequence = if (hasUnboundIntents) unbound!!.nextSequence else 1,
                    active = true
                ))
                if (hasUnboundIntents) mutations.moveScope("unbound", id)
                FeedV2Destination(url, id)
            }
        }
    }

    /** Settings calls this before writing a changed URL to preferences. */
    suspend fun beforeDestinationChange(newUrl: String?) {
        val normalized = newUrl?.takeIf { it.isNotBlank() }?.let(::normalizedUrl)
        database.withTransaction {
            val active = states.active() ?: return@withTransaction
            if (active.bindingUrl != normalized) {
                states.put(active.copy(suspended = true, generation = active.generation + 1,
                    lastOutcome = "server_changed", lastDiagnostic = "Destination changed"))
            }
        }
    }

    /** Explicit review of a replaced server. Old sent payloads remain suspended in their scope. */
    suspend fun prepareServerReconciliation(): Boolean = database.withTransaction {
        val old = states.active() ?: return@withTransaction false
        if (!old.suspended) return@withTransaction false
        val newUrl = settings.getGhostwriterUrl()?.let(::normalizedUrl)?.takeIf { it.isNotBlank() }
            ?: return@withTransaction false
        val id = uuid()
        var sequence = 1L
        val oldRows = mutations.forScope(old.serverKey).groupBy { it.url }
        states.put(old.copy(active = false, generation = old.generation + 1))
        for (feed in feeds.getAllRealFeedsIncludingHidden()) {
            val proposals = oldRows[feed.url].orEmpty().sortedWith(
                compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })
            if (proposals.isEmpty()) {
                mutations.insert(FeedMutationEntity(uuid(), id, feed.url,
                    if (feed.hiddenDelete) "delete" else "upsert", null,
                    if (feed.hiddenDelete) "{}" else encode(fields(feed)), feed.mutationRevision,
                    "legacy_unresolved", createdAt = System.currentTimeMillis(),
                    sequence = sequence, queueOrder = sequence))
                sequence++
            } else for (proposal in proposals) {
                mutations.insert(proposal.copy(opId = uuid(), serverKey = id, baseVersion = null,
                    state = "needs_resolution", serverSnapshotJson = null, sent = false,
                    sequence = sequence, queueOrder = sequence,
                    rejectionCode = null, rejectionMessage = null))
                sequence++
            }
        }
        states.put(FeedSyncStateEntity(serverKey = id, bindingUrl = newUrl,
            configurationId = id, nextSequence = sequence, active = true))
        true
    }

    private suspend fun localState(): FeedSyncStateEntity {
        val existing = states.active() ?: states.byKey("unbound")
        if (existing != null) return existing
        return FeedSyncStateEntity("unbound").also { states.put(it) }
    }

    private fun uuid() = UUID.randomUUID().toString()
    private fun fields(feed: FeedEntity) = FeedDirtyFieldsV2(
        title = feed.name, isActive = feed.isEnabled,
        mode = if (feed.mode == ProcessingMode.BRIEFING) "summarize" else "raw",
        maxArticles = feed.maxArticles
    )
    private fun encode(fields: FeedDirtyFieldsV2) = feedV2Json.encodeToString(fields)
    private fun decode(row: FeedMutationEntity): FeedDirtyFieldsV2 = feedV2Json.decodeFromString(row.fieldsJson)
    private fun snapshot(row: FeedSnapshotV2) = feedV2Json.encodeToString(row)
    private fun parseSnapshot(value: String?): FeedSnapshotV2? = value?.let { feedV2Json.decodeFromString(it) }
    private fun sameFields(proposal: FeedDirtyFieldsV2, remote: FeedSnapshotV2): Boolean =
        remote.kind == "feed" && proposal.title == remote.title &&
            proposal.isActive == remote.isActive && proposal.mode == remote.mode &&
            proposal.maxArticles == remote.maxArticles

    private fun fromRemote(current: FeedEntity?, remote: FeedSnapshotV2): FeedEntity {
        require(remote.kind == "feed")
        return (current ?: FeedEntity(remote.url, remote.title!!,
            if (remote.mode == "summarize") ProcessingMode.BRIEFING else ProcessingMode.FIDELITY)).copy(
            name = remote.title!!, mode = if (remote.mode == "summarize") ProcessingMode.BRIEFING else ProcessingMode.FIDELITY,
            maxArticles = remote.maxArticles!!, isEnabled = remote.isActive!!,
            serverId = remote.id, serverVersion = remote.version,
            serverSnapshotJson = snapshot(remote), hiddenDelete = false, locallyModified = false
        )
    }

    /** All user edits, including local-only edits, create an intent in the same write transaction. */
    suspend fun saveLocal(feed: Feed) {
        require(isFeedUrlV2(feed.url) && feed.maxArticles >= 0 && feed.name.isNotBlank())
        database.withTransaction {
            val old = feeds.getFeedByUrl(feed.url)
            val state = localState()
            val nextRevision = (old?.mutationRevision ?: 0) + 1
            val updated = (old ?: FeedEntity(feed.url, feed.name, feed.mode)).copy(
                name = feed.name, mode = feed.mode, maxArticles = feed.maxArticles,
                isEnabled = feed.isEnabled, lastFetched = old?.lastFetched ?: feed.lastFetched,
                hiddenDelete = false, mutationRevision = nextRevision, locallyModified = true
            )
            val changed = old == null || old.hiddenDelete || fields(old) != fields(updated)
            feeds.insertFeed(updated)
            if (changed) {
                val head = mutations.forUrl(feed.url).firstOrNull { it.serverKey == state.serverKey }
                val base = head?.baseVersion ?: old?.serverVersion
                val dirty = if (old == null || base == null || old.hiddenDelete) fields(updated) else FeedDirtyFieldsV2(
                    title = updated.name.takeIf { it != old.name },
                    isActive = updated.isEnabled.takeIf { it != old.isEnabled },
                    mode = (if (updated.mode == ProcessingMode.BRIEFING) "summarize" else "raw")
                        .takeIf { updated.mode != old.mode },
                    maxArticles = updated.maxArticles.takeIf { it != old.maxArticles }
                ).let { if (it.isEmpty()) fields(updated) else it }
                mutations.insert(FeedMutationEntity(uuid(), state.serverKey, feed.url, "upsert", base,
                    encode(dirty), nextRevision, "queued", createdAt = System.currentTimeMillis(),
                    sequence = state.nextSequence, queueOrder = state.nextSequence))
                states.put(state.copy(nextSequence = state.nextSequence + 1))
            }
        }
    }

    suspend fun deleteLocal(url: String) {
        database.withTransaction {
            val old = feeds.getFeedByUrl(url) ?: return@withTransaction
            if (old.hiddenDelete || url.startsWith("synthetic://")) return@withTransaction
            val state = localState()
            val revision = old.mutationRevision + 1
            feeds.insertFeed(old.copy(hiddenDelete = true, mutationRevision = revision, locallyModified = true))
            mutations.insert(FeedMutationEntity(uuid(), state.serverKey, url, "delete", old.serverVersion,
                "{}", revision, "queued", createdAt = System.currentTimeMillis(),
                sequence = state.nextSequence, queueOrder = state.nextSequence))
            states.put(state.copy(nextSequence = state.nextSequence + 1))
        }
    }

    fun unresolved() = mutations.unresolvedFlow()
    fun status() = states.activeFlow()

    suspend fun recordOutcome(outcome: FeedSyncV2Outcome) {
        database.withTransaction {
            val state = states.active() ?: return@withTransaction
            // A run invalidated by a destination or server-identity change cannot hide Review.
            if (state.suspended) return@withTransaction
            val label = when (outcome) {
                is FeedSyncV2Outcome.Complete -> "complete"
                is FeedSyncV2Outcome.Partial -> "partial"
                is FeedSyncV2Outcome.Failed -> "failed"
                FeedSyncV2Outcome.ServerChanged -> "server_changed"
                FeedSyncV2Outcome.ServerUpgradeRequired -> "server_upgrade_required"
                FeedSyncV2Outcome.NotConfigured -> "not_configured"
            }
            states.put(state.copy(lastOutcome = label,
                lastDiagnostic = when (outcome) {
                    is FeedSyncV2Outcome.Partial -> "${outcome.pending} pending; ${outcome.conflicts} conflicts; ${outcome.rejected} rejected"
                    is FeedSyncV2Outcome.Failed -> "${outcome.phase}: ${outcome.message}"
                    else -> null
                }))
        }
    }

    private fun tokenValid(token: FeedV2RunToken): Boolean = synchronized(gate) { activeToken == token.value }
    private fun runScope(token: FeedV2RunToken): Pair<FeedV2Destination, Long>? =
        synchronized(gate) { if (activeToken == token.value) activeRun else null }
    private suspend fun checked(token: FeedV2RunToken, binding: FeedV2Binding? = null): FeedSyncStateEntity? {
        val scope = runScope(token) ?: return null
        val state = states.active() ?: return null
        if (state.suspended || state.generation != scope.second ||
            FeedV2Destination(state.bindingUrl!!, state.configurationId!!) != scope.first ||
            binding?.generation?.let { it != state.generation } == true ||
            binding?.destination?.let { it != FeedV2Destination(state.bindingUrl!!, state.configurationId!!) } == true ||
            binding?.serverInstanceId?.let { !it.equals(state.serverInstanceId, ignoreCase = true) } == true) return null
        return state
    }
    private fun bound(state: FeedSyncStateEntity) = FeedV2Binding(
        FeedV2Destination(state.bindingUrl!!, state.configurationId!!), state.serverInstanceId,
        state.cursorVersion, state.firstBindingComplete, state.generation, state.suspended
    )
    private suspend fun <T> safely(block: suspend () -> FeedV2StoreResult<T>): FeedV2StoreResult<T> = try {
        block()
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (error: Exception) {
        FeedV2StoreResult.Failure(error.message ?: "Local feed storage failure")
    }

    override suspend fun beginSyncRun(destination: FeedV2Destination): FeedV2StoreResult<FeedV2RunToken> {
        val state = states.active() ?: return FeedV2StoreResult.StaleBinding
        if (state.bindingUrl != destination.normalizedBaseUrl || state.configurationId != destination.configurationId)
            return FeedV2StoreResult.StaleBinding
        synchronized(gate) {
            if (activeToken != null) return FeedV2StoreResult.Busy
            activeToken = uuid()
            activeRun = destination to state.generation
            return FeedV2StoreResult.Success(FeedV2RunToken(activeToken!!))
        }
    }
    override suspend fun endSyncRun(token: FeedV2RunToken) {
        synchronized(gate) { if (activeToken == token.value) { activeToken = null; activeRun = null } }
    }
    override suspend fun getServerIdentity(token: FeedV2RunToken): FeedV2StoreResult<FeedV2Binding?> = safely {
        val scope = runScope(token) ?: return@safely FeedV2StoreResult.StaleBinding
        val state = states.active() ?: return@safely FeedV2StoreResult.StaleBinding
        if (state.generation != scope.second ||
            FeedV2Destination(state.bindingUrl!!, state.configurationId!!) != scope.first)
            FeedV2StoreResult.StaleBinding else FeedV2StoreResult.Success(bound(state))
    }
    override suspend fun suspendBinding(token: FeedV2RunToken, binding: FeedV2Binding, reason: String): FeedV2StoreResult<Unit> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            states.put(state.copy(suspended = true, generation = state.generation + 1,
                lastOutcome = "server_changed", lastDiagnostic = reason))
            FeedV2StoreResult.Success(Unit)
        }
    }
    override suspend fun reconcileAndBindFullSnapshot(
        token: FeedV2RunToken, destination: FeedV2Destination, snapshot: FeedChangesV2Response
    ): FeedV2StoreResult<FeedV2Binding> = safely {
        database.withTransaction {
            val state = checked(token) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            if (state.bindingUrl != destination.normalizedBaseUrl || state.configurationId != destination.configurationId ||
                state.firstBindingComplete) return@withTransaction FeedV2StoreResult.StaleBinding
            val remote = snapshot.changes.associateBy { it.url }
            for (feed in feeds.getAllRealFeedsIncludingHidden()) {
                val head = mutations.forUrl(feed.url).firstOrNull { it.serverKey == state.serverKey }
                val row = remote[feed.url]
                if (head == null) {
                    if (row?.kind == "feed") feeds.insertFeed(fromRemote(feed, row))
                    else if (row?.kind == "tombstone") feeds.insertFeed(feed.copy(hiddenDelete = true,
                        serverId = row.id, serverVersion = row.version, serverSnapshotJson = snapshot(row)))
                    continue
                }
                if (head.state == "legacy_unresolved" && row != null && sameFields(decode(head), row)) {
                    mutations.deleteById(head.opId)
                    val successor = mutations.forUrl(feed.url)
                        .filter { it.serverKey == state.serverKey }
                        .minWithOrNull(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })
                    if (successor != null) mutations.update(successor.copy(
                        baseVersion = if (successor.sent) successor.baseVersion else row.version,
                        state = if (successor.sent) "needs_resolution" else successor.state,
                        serverSnapshotJson = snapshot(row)))
                    feeds.insertFeed(if (successor == null) fromRemote(feed, row) else feed.copy(
                        serverId = row.id, serverVersion = row.version,
                        serverSnapshotJson = snapshot(row), locallyModified = true))
                } else if (head.state == "legacy_unresolved" || head.state == "needs_resolution" ||
                    row != null || head.kind == "delete") {
                    mutations.update(head.copy(state = "needs_resolution", serverSnapshotJson = row?.let(::snapshot)))
                    feeds.insertFeed(if (row?.kind == "feed" && head.kind != "delete") fromRemote(feed, row)
                        else feed.copy(hiddenDelete = true, serverId = row?.id ?: feed.serverId,
                            serverVersion = row?.version ?: feed.serverVersion,
                            serverSnapshotJson = row?.let(::snapshot)))
                }
            }
            for (row in snapshot.changes) {
                if (row.kind == "feed" && !row.url.startsWith("synthetic://") &&
                    feeds.getFeedByUrl(row.url) == null) {
                    feeds.insertFeed(fromRemote(null, row))
                }
            }
            val updated = state.copy(serverInstanceId = snapshot.serverInstanceId,
                cursorVersion = snapshot.serverVersion, firstBindingComplete = true)
            states.put(updated)
            FeedV2StoreResult.Success(bound(updated))
        }
    }
    override suspend fun loadPendingMutations(token: FeedV2RunToken, binding: FeedV2Binding, maxItems: Int): FeedV2StoreResult<List<SentFeedMutationV2>> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            val heads = mutations.forScope(state.serverKey).groupBy { it.url }
                .values.mapNotNull { rows -> rows.minWithOrNull(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence }) }
                .filter { it.state == "queued" }.sortedWith(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })
                .take(maxItems.coerceIn(0, 100))
            val result = heads.map { row ->
                if (!row.sent) mutations.update(row.copy(sent = true))
                SentFeedMutationV2(row.opId, row.url, row.sequence, row.localRevision,
                    FeedMutationV2(row.opId, row.url, row.kind, row.baseVersion,
                        if (row.kind == "delete") null else decode(row)))
            }
            FeedV2StoreResult.Success(result)
        }
    }
    override suspend fun pendingSummary(token: FeedV2RunToken, binding: FeedV2Binding): FeedV2StoreResult<FeedV2WorkSummary> = safely {
        val state = checked(token, binding) ?: return@safely FeedV2StoreResult.StaleBinding
        val rows = mutations.forScope(state.serverKey)
        val heads = rows.groupBy { it.url }.values.mapNotNull { it.minWithOrNull(compareBy<FeedMutationEntity> { row -> row.queueOrder }.thenBy { row -> row.sequence }) }
        FeedV2StoreResult.Success(FeedV2WorkSummary(
            eligible = heads.count { it.state == "queued" },
            blockedConflicts = heads.count { it.state == "needs_resolution" },
            rejected = heads.count { it.state == "rejected" },
            unsentSuccessors = rows.size - heads.size,
            needsResolution = heads.count { it.state == "legacy_unresolved" }
        ))
    }
    override suspend fun acknowledge(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
        sentRevision: Long, current: FeedSnapshotV2?): FeedV2StoreResult<Unit> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            val row = mutations.byId(opId) ?: return@withTransaction FeedV2StoreResult.StaleSentRevision
            if (row.serverKey != state.serverKey || !row.sent || row.localRevision != sentRevision || row.state != "queued")
                return@withTransaction FeedV2StoreResult.StaleSentRevision
            val feed = feeds.getFeedByUrl(row.url)
            val older = feed?.serverVersion?.let { current != null && current.version < it } == true
            mutations.deleteById(row.opId)
            val successors = mutations.forUrl(row.url).filter { it.serverKey == state.serverKey }
                .sortedWith(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })
            if (feed != null && current != null && !older) {
                feeds.insertFeed(if (successors.isEmpty() && current.kind == "feed") fromRemote(feed, current)
                    else feed.copy(serverId = current.id, serverVersion = current.version,
                        serverSnapshotJson = snapshot(current), hiddenDelete = if (successors.isEmpty()) current.kind == "tombstone" else feed.hiddenDelete,
                        locallyModified = successors.isNotEmpty()))
            } else if (feed != null && successors.isEmpty()) {
                feeds.insertFeed(feed.copy(locallyModified = false))
            }
            if (successors.isNotEmpty()) {
                val first = successors.first()
                if (older || first.sent) mutations.update(first.copy(state = "needs_resolution",
                    serverSnapshotJson = if (older) feed?.serverSnapshotJson else current?.let(::snapshot)))
                else mutations.update(first.copy(baseVersion = current?.version,
                    state = if (first.state == "queued") "queued" else "needs_resolution"))
            }
            FeedV2StoreResult.Success(Unit)
        }
    }
    override suspend fun recordConflict(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
        sentRevision: Long, current: FeedSnapshotV2): FeedV2StoreResult<Unit> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            val row = mutations.byId(opId) ?: return@withTransaction FeedV2StoreResult.StaleSentRevision
            if (row.serverKey != state.serverKey || !row.sent || row.localRevision != sentRevision)
                return@withTransaction FeedV2StoreResult.StaleSentRevision
            val feed = feeds.getFeedByUrl(row.url)
            val effective = if (feed?.serverVersion?.let { it > current.version } == true)
                parseSnapshot(feed.serverSnapshotJson) ?: current else current
            mutations.update(row.copy(state = "needs_resolution", serverSnapshotJson = snapshot(effective)))
            if (feed != null && (feed.serverVersion == null || effective.version >= feed.serverVersion))
                feeds.insertFeed(if (effective.kind == "feed" && row.kind != "delete") fromRemote(feed, effective)
                    else feed.copy(serverId = effective.id, serverVersion = effective.version,
                        serverSnapshotJson = snapshot(effective), hiddenDelete = true))
            FeedV2StoreResult.Success(Unit)
        }
    }
    override suspend fun recordRejection(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
        sentRevision: Long, code: String, message: String?): FeedV2StoreResult<Unit> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            val row = mutations.byId(opId) ?: return@withTransaction FeedV2StoreResult.StaleSentRevision
            if (row.serverKey != state.serverKey || !row.sent || row.localRevision != sentRevision)
                return@withTransaction FeedV2StoreResult.StaleSentRevision
            mutations.update(row.copy(state = "rejected", rejectionCode = code, rejectionMessage = message))
            FeedV2StoreResult.Success(Unit)
        }
    }
    override suspend fun applyServerChangesAndCursor(token: FeedV2RunToken, binding: FeedV2Binding,
        changes: FeedChangesV2Response): FeedV2StoreResult<Unit> = safely {
        database.withTransaction {
            val state = checked(token, binding) ?: return@withTransaction FeedV2StoreResult.StaleBinding
            for (row in changes.changes) {
                if (row.url.startsWith("synthetic://")) continue
                val current = feeds.getFeedByUrl(row.url)
                val pending = mutations.forUrl(row.url).filter { it.serverKey == state.serverKey }
                    .minWithOrNull(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })
                if (pending != null) {
                    if (current != null && (current.serverVersion == null || row.version >= current.serverVersion)) {
                        val newer = current.serverVersion != null && row.version > current.serverVersion
                        val proposalVersion = parseSnapshot(pending.serverSnapshotJson)?.version
                        if (proposalVersion == null || row.version > proposalVersion) {
                            mutations.update(pending.copy(
                                state = if (newer && pending.state == "queued" && !pending.sent)
                                    "needs_resolution" else pending.state,
                                serverSnapshotJson = snapshot(row)))
                        }
                        feeds.insertFeed(if (newer && row.kind == "feed" && pending.kind != "delete")
                            fromRemote(current, row).copy(locallyModified = true)
                            else current.copy(serverId = row.id, serverVersion = row.version,
                                serverSnapshotJson = snapshot(row), hiddenDelete = current.hiddenDelete || row.kind == "tombstone"))
                    }
                } else if (row.kind == "feed") feeds.insertFeed(fromRemote(current, row))
                else if (current != null) feeds.insertFeed(current.copy(hiddenDelete = true, serverId = row.id,
                    serverVersion = row.version, serverSnapshotJson = snapshot(row)))
            }
            states.put(state.copy(cursorVersion = changes.serverVersion, lastOutcome = "pulled", lastDiagnostic = null))
            FeedV2StoreResult.Success(Unit)
        }
    }

    /** Explicit choices never mutate a sent payload. Dependent successors remain blocked. */
    suspend fun resolve(opId: String, action: String): Boolean = database.withTransaction {
        val row = mutations.byId(opId) ?: return@withTransaction false
        if (row.state !in setOf("needs_resolution", "rejected")) return@withTransaction false
        if (mutations.forUrl(row.url).filter { it.serverKey == row.serverKey }
                .minWithOrNull(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })?.opId != opId)
            return@withTransaction false
        val state = states.byKey(row.serverKey) ?: return@withTransaction false
        if (!state.active || state.suspended) return@withTransaction false
        val feed = feeds.getFeedByUrl(row.url)
        val proposalServer = parseSnapshot(row.serverSnapshotJson)
        val feedServer = parseSnapshot(feed?.serverSnapshotJson)
        val server = if (feedServer != null &&
            (proposalServer == null || feedServer.version > proposalServer.version)) feedServer else proposalServer
        val successors = mutations.forUrl(row.url).filter { it.serverKey == state.serverKey && it.queueOrder > row.queueOrder }
        val keep = action in setOf("keep_server", "keep_feed", "keep_removed", "discard")
        val apply = action in setOf("apply_mine", "delete_anyway", "add_to_server") ||
            (action == "correct" && row.state == "rejected" && row.kind == "delete")
        if (!keep && !apply) return@withTransaction false
        mutations.deleteById(row.opId)
        successors.forEach { mutations.update(it.copy(state = "needs_resolution",
            serverSnapshotJson = server?.let(::snapshot))) }
        if (keep) {
            if (feed != null) feeds.insertFeed(if (server?.kind == "feed") fromRemote(feed, server)
                else feed.copy(hiddenDelete = true, locallyModified = successors.isNotEmpty()))
        } else {
            val proposed = decode(row)
            val base = server?.version
            var resolvedFields = row.fieldsJson
            if (feed != null) {
                val corrected = if (row.kind == "delete") feed.copy(hiddenDelete = true)
                else feed.copy(name = proposed.title ?: feed.name,
                    mode = when (proposed.mode) { "summarize" -> ProcessingMode.BRIEFING; "raw" -> ProcessingMode.FIDELITY; else -> feed.mode },
                    isEnabled = proposed.isActive ?: feed.isEnabled,
                    maxArticles = proposed.maxArticles ?: feed.maxArticles, hiddenDelete = false)
                feeds.insertFeed(corrected.copy(locallyModified = true, mutationRevision = feed.mutationRevision + 1))
                if (row.kind == "upsert" && server == null) resolvedFields = encode(fields(corrected))
            }
            mutations.insert(FeedMutationEntity(uuid(), state.serverKey, row.url, row.kind, base,
                if (row.kind == "delete") "{}" else resolvedFields,
                (feed?.mutationRevision ?: 0) + 1, "queued", createdAt = System.currentTimeMillis(),
                sequence = state.nextSequence, queueOrder = row.queueOrder))
            states.put(state.copy(nextSequence = state.nextSequence + 1))
        }
        true
    }

    /** Correct a rejected upsert with fresh values and a new operation identity. */
    suspend fun correctRejected(opId: String, title: String, mode: ProcessingMode,
        enabled: Boolean, maxArticles: Int): Boolean = database.withTransaction {
        if (title.isBlank() || maxArticles < 0) return@withTransaction false
        val row = mutations.byId(opId) ?: return@withTransaction false
        if (row.state != "rejected" || row.kind != "upsert") return@withTransaction false
        if (mutations.forUrl(row.url).filter { it.serverKey == row.serverKey }
                .minWithOrNull(compareBy<FeedMutationEntity> { it.queueOrder }.thenBy { it.sequence })?.opId != opId)
            return@withTransaction false
        val state = states.byKey(row.serverKey) ?: return@withTransaction false
        if (!state.active || state.suspended) return@withTransaction false
        val feed = feeds.getFeedByUrl(row.url) ?: return@withTransaction false
        val current = parseSnapshot(feed.serverSnapshotJson)
        val corrected = feed.copy(name = title, mode = mode, isEnabled = enabled,
            maxArticles = maxArticles, hiddenDelete = false, locallyModified = true,
            mutationRevision = feed.mutationRevision + 1)
        val fields = FeedDirtyFieldsV2(title, enabled,
            if (mode == ProcessingMode.BRIEFING) "summarize" else "raw", maxArticles)
        mutations.deleteById(opId)
        mutations.forUrl(row.url).filter { it.serverKey == state.serverKey && it.queueOrder > row.queueOrder }
            .forEach { mutations.update(it.copy(state = "needs_resolution",
                serverSnapshotJson = current?.let(::snapshot))) }
        feeds.insertFeed(corrected)
        mutations.insert(FeedMutationEntity(uuid(), state.serverKey, row.url, "upsert", current?.version,
            encode(fields), corrected.mutationRevision, "queued", createdAt = System.currentTimeMillis(),
            sequence = state.nextSequence, queueOrder = row.queueOrder))
        states.put(state.copy(nextSequence = state.nextSequence + 1))
        true
    }
}
