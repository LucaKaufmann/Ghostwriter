import Foundation
import SwiftData
import Domain
import EpilogueShared

/// Serializes every v2 feed transaction on the main actor. Each operation owns
/// one non-autosaving context and saves feed, intent, binding and cursor once.
@MainActor
final class IOSFeedV2StoreEngine {
    private let container: ModelContainer
    private var activeToken: String?
    private var activeGeneration: Int64?
    private var activeDestination: String?
    #if DEBUG
    var failNextSaveForTesting = false
    #endif

    init(container: ModelContainer) { self.container = container }

    private func transaction<T>(_ body: (ModelContext) throws -> T) throws -> T {
        let context = ModelContext(container)
        context.autosaveEnabled = false
        do {
            let value = try body(context)
            if context.hasChanges {
                #if DEBUG
                if failNextSaveForTesting {
                    failNextSaveForTesting = false
                    throw StoreError.injectedSaveFailure
                }
                #endif
                try context.save()
            }
            return value
        } catch {
            context.rollback()
            throw error
        }
    }

    private func state(_ context: ModelContext) throws -> FeedSyncState {
        if let existing = try context.fetch(FetchDescriptor<FeedSyncState>()).first { return existing }
        let created = FeedSyncState()
        context.insert(created)
        return created
    }

    private func mutations(_ context: ModelContext) throws -> [FeedMutation] {
        try context.fetch(FetchDescriptor<FeedMutation>()).sorted { $0.sequence < $1.sequence }
    }

    private func feed(_ url: String, _ context: ModelContext) throws -> Domain.Feed? {
        try context.fetch(FetchDescriptor<Domain.Feed>(predicate: #Predicate { $0.url == url })).first
    }

    private func scope(_ destination: FeedV2Destination) -> String {
        destination.normalizedBaseUrl + "\n" + destination.configurationId
    }

    private func validFeedURL(_ url: String) -> Bool {
        guard url == url.trimmingCharacters(in: .whitespacesAndNewlines),
              let separator = url.range(of: "://"),
              ["http", "https"].contains(url[..<separator.lowerBound].lowercased())
        else { return false }
        let remainder = url[separator.upperBound...]
        let authority = remainder.prefix { !"/?#".contains($0) }
        return !authority.isEmpty && !authority.contains("@") &&
            !authority.contains(where: \.isWhitespace)
    }

    private func normalizedDestination(_ rawURL: String?) -> String? {
        let value = rawURL?.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return value?.isEmpty == false ? value : nil
    }

    func destination(for rawURL: String) throws -> FeedV2Destination {
        guard let normalized = normalizedDestination(rawURL) else { throw StoreError.invalidEdit }
        return try transaction { context in
            let value = try state(context)
            if value.destinationURL == nil {
                value.destinationURL = normalized
                value.configurationId = UUID().uuidString.lowercased()
                value.generation += 1
            } else if value.destinationURL != normalized {
                // Preserve old scoped intents; require an explicit new binding.
                value.destinationURL = normalized
                value.configurationId = UUID().uuidString.lowercased()
                value.serverInstanceId = nil
                value.cursorVersion = nil
                value.firstReconciliationComplete = false
                value.suspended = true
                value.generation += 1
            }
            return FeedV2Destination(normalizedBaseUrl: normalized,
                                     configurationId: value.configurationId!)
        }
    }

    /// Capture before an asynchronous settings read. A later URL edit changes
    /// generation, so a stale read cannot authorize a resolution decision.
    func resolutionGeneration() throws -> Int64 {
        let context = ModelContext(container)
        guard let value = try context.fetch(FetchDescriptor<FeedSyncState>()).first else {
            throw StoreError.staleBinding
        }
        return value.generation
    }

    func requireResolutionDestination(_ configuredURL: String?, generation: Int64) throws {
        guard let normalized = normalizedDestination(configuredURL) else {
            throw StoreError.staleBinding
        }
        let context = ModelContext(container)
        guard let value = try context.fetch(FetchDescriptor<FeedSyncState>()).first,
              value.destinationURL == normalized,
              value.generation == generation,
              !value.suspended else { throw StoreError.staleBinding }
    }

    func startNewBinding() throws {
        try transaction { context in
            let value = try state(context)
            guard value.destinationURL != nil else { throw StoreError.invalidEdit }
            value.configurationId = UUID().uuidString.lowercased()
            value.suspended = false
            value.serverInstanceId = nil
            value.cursorVersion = nil
            value.firstReconciliationComplete = false
            value.generation += 1
            // Feed rows are shared UI cache, but their versions belong to the
            // previous instance. Hide them from local generation until the
            // new full snapshot establishes current server ownership.
            let oldScopedURLs = Set(try mutations(context)
                .filter { $0.scopeKey != "__unbound__" }.map(\.url))
            for feed in try context.fetch(FetchDescriptor<Domain.Feed>()) {
                guard !feed.url.hasPrefix("synthetic://"),
                      feed.serverId != nil || feed.serverVersion != nil ||
                      oldScopedURLs.contains(feed.url) else { continue }
                feed.serverId = nil
                feed.serverVersion = nil
                feed.isLocallyDeleted = true
            }
        }
    }

    private func binding(_ state: FeedSyncState) -> FeedV2Binding? {
        guard let url = state.destinationURL, let id = state.configurationId else { return nil }
        return FeedV2Binding(
            destination: FeedV2Destination(normalizedBaseUrl: url, configurationId: id),
            serverInstanceId: state.serverInstanceId,
            cursorVersion: state.cursorVersion.map { KotlinLong(longLong: $0) },
            firstReconciliationComplete: state.firstReconciliationComplete,
            generation: state.generation, suspended: state.suspended)
    }

    private func checked(_ token: FeedV2RunToken, _ context: ModelContext,
                         binding expected: FeedV2Binding? = nil) throws -> FeedSyncState {
        guard activeToken == token.value else { throw StoreError.staleBinding }
        let value = try state(context)
        guard value.generation == activeGeneration,
              value.destinationURL == activeDestination else { throw StoreError.staleBinding }
        if let expected {
            guard value.generation == expected.generation,
                  value.destinationURL == expected.destination.normalizedBaseUrl,
                  value.configurationId == expected.destination.configurationId,
                  !value.suspended,
                  value.serverInstanceId?.lowercased() == expected.serverInstanceId?.lowercased()
            else { throw StoreError.staleBinding }
        }
        return value
    }

    func begin(_ destination: FeedV2Destination) throws -> FeedV2RunToken {
        guard activeToken == nil else { throw StoreError.busy }
        let generation = try transaction { context in
            let value = try state(context)
            if value.destinationURL == nil {
                value.destinationURL = destination.normalizedBaseUrl
                value.configurationId = destination.configurationId
                value.generation += 1
            } else if value.destinationURL != destination.normalizedBaseUrl ||
                        value.configurationId != destination.configurationId {
                value.suspended = true
                value.generation += 1
            }
            return value.generation
        }
        let token = UUID().uuidString.lowercased()
        activeToken = token
        activeGeneration = generation
        activeDestination = destination.normalizedBaseUrl
        return FeedV2RunToken(value: token)
    }

    func end(_ token: FeedV2RunToken) {
        if activeToken == token.value {
            activeToken = nil
            activeGeneration = nil
            activeDestination = nil
        }
    }

    func identity(_ token: FeedV2RunToken) throws -> FeedV2Binding? {
        try transaction { context in binding(try checked(token, context)) }
    }

    func suspend(_ token: FeedV2RunToken, _ expected: FeedV2Binding) throws {
        try transaction { context in
            let value = try checked(token, context, binding: expected)
            value.suspended = true
            value.generation += 1
        }
    }

    func suspendForDestinationChange(_ url: String?) throws {
        try transaction { context in
            let value = try state(context)
            guard value.destinationURL != nil,
                  value.destinationURL != url else { return }
            value.suspended = true
            value.generation += 1
        }
    }

    private func setSnapshot(_ row: FeedSnapshotV2, on mutation: FeedMutation) {
        mutation.serverKind = row.kind
        mutation.serverId = row.id
        mutation.serverVersion = row.version
        mutation.serverTitle = row.title
        mutation.serverIsActive = row.isActive?.boolValue
        mutation.serverMode = row.mode
        mutation.serverMaxArticles = row.maxArticles.map { Int($0.intValue) }
    }

    private func copySnapshot(_ source: FeedMutation, to target: FeedMutation) {
        target.serverKind = source.serverKind
        target.serverId = source.serverId
        target.serverVersion = source.serverVersion
        target.serverTitle = source.serverTitle
        target.serverIsActive = source.serverIsActive
        target.serverMode = source.serverMode
        target.serverMaxArticles = source.serverMaxArticles
    }

    private func storedSnapshot(_ mutation: FeedMutation) -> FeedSnapshotV2? {
        guard let kind = mutation.serverKind, let id = mutation.serverId,
              let version = mutation.serverVersion else { return nil }
        return FeedSnapshotV2(
            kind: kind, id: id, url: mutation.url, version: version,
            title: mutation.serverTitle,
            isActive: mutation.serverIsActive.map { KotlinBoolean(bool: $0) },
            mode: mutation.serverMode,
            maxArticles: mutation.serverMaxArticles.map { KotlinInt(int: Int32($0)) })
    }

    private func captureVisibleServerSnapshot(_ feed: Domain.Feed, on mutation: FeedMutation) {
        guard let id = feed.serverId, let version = feed.serverVersion else { return }
        mutation.serverKind = feed.isLocallyDeleted == true ? "tombstone" : "feed"
        mutation.serverId = id
        mutation.serverVersion = version
        if mutation.serverKind == "feed" {
            mutation.serverTitle = feed.name
            mutation.serverIsActive = feed.isEnabled
            mutation.serverMode = feed.mode == .briefing ? "summarize" : "raw"
            mutation.serverMaxArticles = feed.maxArticles
        }
    }

    private func setVisible(_ row: FeedSnapshotV2, context: ModelContext,
                            preserveLocalDelete: Bool) throws {
        let existing = try feed(row.url, context)
        if let existing, let oldVersion = existing.serverVersion, row.version < oldVersion { return }
        if row.kind == "tombstone" {
            if let existing {
                existing.serverId = row.id
                existing.serverVersion = row.version
                existing.isLocallyDeleted = true
            }
            return
        }
        guard let title = row.title, let mode = row.mode,
              let active = row.isActive, let max = row.maxArticles else {
            throw StoreError.invalidSnapshot
        }
        let target = existing ?? Domain.Feed(url: row.url, name: title,
                                       mode: mode == "summarize" ? .briefing : .fidelity)
        if existing == nil { context.insert(target) }
        target.name = title
        target.mode = mode == "summarize" ? .briefing : .fidelity
        target.isEnabled = active.boolValue
        target.maxArticles = Int(max.intValue)
        target.serverId = row.id
        target.serverVersion = row.version
        if !preserveLocalDelete { target.isLocallyDeleted = false }
    }

    private func matches(_ row: FeedSnapshotV2, _ proposal: FeedMutation) -> Bool {
        row.kind == "feed" && row.title == proposal.title &&
        row.isActive?.boolValue == proposal.isActive && row.mode == proposal.mode &&
        row.maxArticles.map { Int($0.intValue) } == proposal.maxArticles
    }

    func reconcile(_ token: FeedV2RunToken, destination: FeedV2Destination,
                   snapshot: FeedChangesV2Response) throws -> FeedV2Binding {
        try transaction { context in
            let value = try checked(token, context)
            guard !value.suspended,
                  value.destinationURL == destination.normalizedBaseUrl,
                  value.configurationId == destination.configurationId,
                  !value.firstReconciliationComplete else { throw StoreError.staleBinding }
            let rows = Dictionary(uniqueKeysWithValues: snapshot.changes.map { ($0.url, $0) })
            let scopeKey = scope(destination)
            let oldMutations = try mutations(context)
            let candidates = oldMutations.filter {
                ($0.scopeKey == "__unbound__" || $0.scopeKey == scopeKey) &&
                !$0.url.hasPrefix("synthetic://") && rows[$0.url] == nil
            }
            var coalesced = Set<String>()
            for group in Dictionary(grouping: candidates, by: \.url).values {
                guard let first = group.first,
                      first.kind == "upsert", first.baseVersion == nil,
                      first.title != nil, first.isActive != nil,
                      first.mode != nil, first.maxArticles != nil else { continue }
                var lastDelete: Int?
                for (index, mutation) in group.enumerated() {
                    // A claimed, blocked, or migrated intent may already be
                    // meaningful to another server. Only a wholly local
                    // initial prefix can collapse to its final deletion.
                    guard mutation.status == "pending", !mutation.sent,
                          mutation.origin != "legacy", mutation.baseVersion == nil else { break }
                    if mutation.kind == "delete" { lastDelete = index }
                }
                guard let lastDelete else { continue }
                let remainder = group.dropFirst(lastDelete + 1)
                if let next = remainder.first {
                    // A re-add promoted to the head must be a sendable,
                    // complete create rather than a sparse successor.
                    guard next.kind == "upsert", next.baseVersion == nil,
                          next.title != nil, next.isActive != nil,
                          next.mode != nil, next.maxArticles != nil else { continue }
                }
                for mutation in group.prefix(lastDelete + 1) {
                    coalesced.insert(mutation.opId)
                    context.delete(mutation)
                }
            }
            var unresolvedDeletes = Set<String>()
            var retainedURLs = Set<String>()
            for mutation in oldMutations where mutation.scopeKey == "__unbound__" ||
                mutation.scopeKey == scopeKey {
                guard !coalesced.contains(mutation.opId) else { continue }
                guard !mutation.url.hasPrefix("synthetic://") else { continue }
                let row = rows[mutation.url]
                mutation.scopeKey = scopeKey
                if mutation.origin == "legacy" {
                    if let row, matches(row, mutation) {
                        try setVisible(row, context: context, preserveLocalDelete: false)
                        context.delete(mutation)
                    } else {
                        mutation.status = "needs_resolution"
                        if let row {
                            setSnapshot(row, on: mutation)
                            try setVisible(row, context: context, preserveLocalDelete: mutation.kind == "delete")
                        } else if let local = try feed(mutation.url, context) {
                            local.isLocallyDeleted = true
                        }
                    }
                } else if let row {
                    mutation.status = "needs_resolution"
                    setSnapshot(row, on: mutation)
                    try setVisible(row, context: context, preserveLocalDelete: mutation.kind == "delete")
                } else if mutation.kind == "delete", !retainedURLs.contains(mutation.url),
                          mutation.status == "pending", !mutation.sent,
                          mutation.baseVersion == nil {
                    // An isolated never-sent delete is already satisfied by
                    // an absent server row. A retained earlier intent needs
                    // this delete as an ordered barrier after its ACK.
                    context.delete(mutation)
                    continue
                }
                retainedURLs.insert(mutation.url)
                if mutation.kind == "delete", row != nil,
                   mutation.status == "needs_resolution" {
                    unresolvedDeletes.insert(mutation.url)
                }
            }
            for row in snapshot.changes where !row.url.hasPrefix("synthetic://") {
                try setVisible(row, context: context,
                               preserveLocalDelete: unresolvedDeletes.contains(row.url))
            }
            value.serverInstanceId = snapshot.serverInstanceId.lowercased()
            value.cursorVersion = snapshot.serverVersion
            value.firstReconciliationComplete = true
            return binding(value)!
        }
    }

    private func payload(_ mutation: FeedMutation) -> SentFeedMutationV2 {
        let fields: FeedDirtyFieldsV2? = mutation.kind == "delete" ? nil : FeedDirtyFieldsV2(
            title: mutation.title,
            isActive: mutation.isActive.map { KotlinBoolean(bool: $0) },
            mode: mutation.mode,
            maxArticles: mutation.maxArticles.map { KotlinInt(int: Int32($0)) })
        let request = FeedMutationV2(opId: mutation.opId, url: mutation.url,
                                     kind: mutation.kind,
                                     baseVersion: mutation.baseVersion.map { KotlinLong(longLong: $0) },
                                     fields: fields)
        return SentFeedMutationV2(opId: mutation.opId, url: mutation.url,
                                  sequence: mutation.sequence,
                                  sentRevision: mutation.localRevision, payload: request)
    }

    func claim(_ token: FeedV2RunToken, _ expected: FeedV2Binding,
               maxItems: Int32) throws -> [SentFeedMutationV2] {
        try transaction { context in
            _ = try checked(token, context, binding: expected)
            let scoped = try mutations(context).filter { $0.scopeKey == scope(expected.destination) }
            var seen = Set<String>()
            var result: [SentFeedMutationV2] = []
            for mutation in scoped {
                guard seen.insert(mutation.url).inserted else { continue }
                guard mutation.status == "pending", result.count < min(Int(maxItems), 100) else { continue }
                if !mutation.sent { mutation.sent = true }
                result.append(payload(mutation))
            }
            return result
        }
    }

    #if DEBUG
    func reconcileEmptyForTesting() throws {
        let destination = try destination(for: "https://server.test")
        let token = try begin(destination)
        defer { end(token) }
        _ = try reconcile(token, destination: destination,
                          snapshot: FeedChangesV2Response(
                            serverInstanceId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                            serverVersion: 0, changes: []))
    }

    struct ClaimedPayloadForTesting: Equatable {
        let opId: String
        let sentRevision: Int64
        let baseVersion: Int64?
        let title: String?
        let isActive: Bool?
        let mode: String?
        let maxArticles: Int?
        let wireJSON: String
    }

    /// Keep Kotlin payload objects inside the app image: the hosted XCTest
    /// bundle cannot link the static shared framework a second time.
    func claimOneForTesting() throws -> ClaimedPayloadForTesting? {
        let destination = try transaction { context -> FeedV2Destination in
            guard let value = binding(try state(context)) else { throw StoreError.staleBinding }
            return value.destination
        }
        let token = try begin(destination)
        defer { end(token) }
        guard let expected = try identity(token) else { throw StoreError.staleBinding }
        guard let operation = try claim(token, expected, maxItems: 10).first else { return nil }
        let wireJSON = FeedMutationBatchV2(
            serverInstanceId: "00000000-0000-4000-8000-000000000001",
            mutations: [operation.payload]).toWireJson()
        return ClaimedPayloadForTesting(
            opId: operation.opId, sentRevision: operation.sentRevision,
            baseVersion: operation.payload.baseVersion?.int64Value,
            title: operation.payload.fields?.title,
            isActive: operation.payload.fields?.isActive?.boolValue,
            mode: operation.payload.fields?.mode,
            maxArticles: operation.payload.fields?.maxArticles.map { Int($0.intValue) },
            wireJSON: wireJSON)
    }

    func acknowledgeForTesting(opId: String, revision: Int64, version: Int64,
                               title: String? = nil) throws {
        let destination = try transaction { context -> FeedV2Destination in
            guard let value = binding(try state(context)) else { throw StoreError.staleBinding }
            return value.destination
        }
        let token = try begin(destination)
        defer { end(token) }
        guard let expected = try identity(token) else { throw StoreError.staleBinding }
        let url = try transaction { context -> String in
            guard let mutation = try mutations(context).first(where: { $0.opId == opId }) else {
                throw StoreError.invalidEdit
            }
            return mutation.url
        }
        let current = FeedSnapshotV2(
            kind: title == nil ? "tombstone" : "feed", id: "server-id", url: url,
            version: version, title: title,
            isActive: title.map { _ in KotlinBoolean(bool: false) },
            mode: title.map { _ in "raw" },
            maxArticles: title.map { _ in KotlinInt(int: 2) })
        try acknowledge(token, expected, opId: opId, revision: revision, current: current)
    }
    #endif

    func summary(_ token: FeedV2RunToken, _ expected: FeedV2Binding) throws -> FeedV2WorkSummary {
        try transaction { context in
            _ = try checked(token, context, binding: expected)
            let scoped = try mutations(context).filter { $0.scopeKey == scope(expected.destination) }
            var first = Set<String>()
            var eligible = 0, conflicts = 0, rejected = 0, successors = 0, resolution = 0
            for mutation in scoped {
                guard first.insert(mutation.url).inserted else { successors += 1; continue }
                switch mutation.status {
                case "pending": eligible += 1
                case "conflict": conflicts += 1
                case "rejected": rejected += 1
                default: resolution += 1
                }
            }
            return FeedV2WorkSummary(eligible: Int32(eligible),
                                     blockedConflicts: Int32(conflicts),
                                     rejected: Int32(rejected),
                                     unsentSuccessors: Int32(successors),
                                     needsResolution: Int32(resolution))
        }
    }

    private func sent(_ context: ModelContext, opId: String,
                      revision: Int64) throws -> FeedMutation {
        guard let found = try mutations(context).first(where: {
            $0.opId.lowercased() == opId.lowercased()
        }), found.sent, found.localRevision == revision else { throw StoreError.staleSentRevision }
        return found
    }

    func acknowledge(_ token: FeedV2RunToken, _ expected: FeedV2Binding,
                     opId: String, revision: Int64, current: FeedSnapshotV2?) throws {
        try transaction { context in
            _ = try checked(token, context, binding: expected)
            let mutation = try sent(context, opId: opId, revision: revision)
            guard mutation.scopeKey == scope(expected.destination) else { throw StoreError.staleBinding }
            let target = try feed(mutation.url, context)
            let older = current.map { $0.version < (target?.serverVersion ?? -1) } ?? false
            let successors = try mutations(context).filter {
                $0.url == mutation.url && $0.scopeKey == mutation.scopeKey &&
                $0.sequence > mutation.sequence
            }
            if let current, !older {
                if successors.isEmpty {
                    try setVisible(current, context: context, preserveLocalDelete: false)
                } else {
                    target?.serverId = current.id
                    target?.serverVersion = current.version
                }
            }
            if let next = successors.first {
                if older {
                    next.status = "needs_resolution"
                    if (mutation.serverVersion ?? -1) >= (next.serverVersion ?? -1) {
                        copySnapshot(mutation, to: next)
                    }
                } else if let current, !next.sent {
                    next.baseVersion = current.version
                    setSnapshot(current, on: next)
                    // The accepted head is now the server baseline. Restore
                    // only the successor's dirty fields to the local display;
                    // its immutable predecessor receipt must not hide a newer
                    // edit made while the request was in flight.
                    if let target {
                        if let title = next.title { target.name = title }
                        if let active = next.isActive { target.isEnabled = active }
                        if let mode = next.mode {
                            target.mode = mode == "summarize" ? .briefing : .fidelity
                        }
                        if let maximum = next.maxArticles { target.maxArticles = maximum }
                        // Queue order still defines the user's latest local
                        // hide/re-add choice when later intents need review.
                        // Their field values remain governed by server-wins.
                        target.isLocallyDeleted = successors.last?.kind == "delete"
                    }
                }
            }
            context.delete(mutation)
            if successors.isEmpty { target?.locallyModified = false }
        }
    }

    func conflict(_ token: FeedV2RunToken, _ expected: FeedV2Binding,
                  opId: String, revision: Int64, current: FeedSnapshotV2) throws {
        try transaction { context in
            _ = try checked(token, context, binding: expected)
            let mutation = try sent(context, opId: opId, revision: revision)
            mutation.status = "conflict"
            let latestVersion = max(mutation.serverVersion ?? -1,
                                    try feed(mutation.url, context)?.serverVersion ?? -1)
            if current.version >= latestVersion {
                setSnapshot(current, on: mutation)
                try setVisible(current, context: context,
                               preserveLocalDelete: mutation.kind == "delete")
            }
        }
    }

    func reject(_ token: FeedV2RunToken, _ expected: FeedV2Binding,
                opId: String, revision: Int64, code: String, message: String?) throws {
        try transaction { context in
            _ = try checked(token, context, binding: expected)
            let mutation = try sent(context, opId: opId, revision: revision)
            mutation.status = "rejected"
            mutation.rejectionCode = code
            mutation.rejectionMessage = message
        }
    }

    func apply(_ token: FeedV2RunToken, _ expected: FeedV2Binding,
               changes: FeedChangesV2Response) throws {
        try transaction { context in
            let value = try checked(token, context, binding: expected)
            let scoped = try mutations(context).filter { $0.scopeKey == scope(expected.destination) }
            for row in changes.changes where !row.url.hasPrefix("synthetic://") {
                let related = scoped.filter { $0.url == row.url }
                if let head = related.first {
                    if head.status == "pending", !head.sent,
                       row.version > (head.baseVersion ?? -1) {
                        head.status = "needs_resolution"
                    }
                    if row.version >= (head.serverVersion ?? -1) {
                        setSnapshot(row, on: head)
                    }
                }
                try setVisible(row, context: context,
                               preserveLocalDelete: related.first?.kind == "delete")
            }
            value.cursorVersion = changes.serverVersion
        }
    }

    func edit(url: String, title: String, mode: Domain.ProcessingMode,
              isEnabled: Bool, maxArticles: Int) throws {
        guard validFeedURL(url) else { throw StoreError.invalidURL }
        guard !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw StoreError.invalidTitle
        }
        guard maxArticles >= 0, maxArticles <= Int32.max else {
            throw StoreError.invalidEdit
        }
        try transaction { context in
            let value = try state(context)
            let existing = try feed(url, context)
            let prior = try mutations(context).filter { $0.url == url }.last
            let changedTitle = existing?.name != title
            let changedMode = existing?.mode != mode
            let changedEnabled = existing?.isEnabled != isEnabled
            let changedCap = existing?.maxArticles != maxArticles
            let originalVersion = existing?.serverVersion
            guard existing == nil || changedTitle || changedMode || changedEnabled ||
                    changedCap || existing?.isLocallyDeleted == true else { return }
            let scopeKey = value.destinationURL.flatMap { url in
                value.configurationId.map { url + "\n" + $0 }
            } ?? "__unbound__"
            // A first create or re-add of a locally deleted feed needs all
            // fields, including when the user keeps its displayed values.
            // Later upserts for the same queued create carry only changes;
            // copied fields could replay an obsolete rejected value.
            let full = existing == nil || existing?.isLocallyDeleted == true ||
                (originalVersion == nil &&
                 !(prior?.scopeKey == scopeKey && prior?.kind == "upsert"))
            let revision = (existing?.mutationRevision ?? 0) + (existing == nil ? 0 : 1)
            let mutation = FeedMutation(
                url: url, scopeKey: scopeKey, kind: "upsert",
                baseVersion: originalVersion,
                title: full || changedTitle ? title : nil,
                isActive: full || changedEnabled ? isEnabled : nil,
                mode: full || changedMode ? (mode == .briefing ? "summarize" : "raw") : nil,
                maxArticles: full || changedCap ? maxArticles : nil,
                sequence: value.nextSequence, localRevision: revision)
            if let existing, prior?.scopeKey != scopeKey {
                captureVisibleServerSnapshot(existing, on: mutation)
            }
            if existing == nil && prior == nil {
                let created = Domain.Feed(url: url, name: title, mode: mode,
                                   maxArticles: maxArticles, isEnabled: isEnabled)
                context.insert(created)
            } else if let existing {
                existing.name = title
                existing.mode = mode
                existing.isEnabled = isEnabled
                existing.maxArticles = maxArticles
                existing.isLocallyDeleted = false
                existing.locallyModified = true
                existing.mutationRevision = revision
            }
            context.insert(mutation)
            value.nextSequence += 1
        }
    }

    func delete(url: String) throws {
        try transaction { context in
            guard let target = try feed(url, context), !url.hasPrefix("synthetic://") else {
                throw StoreError.invalidEdit
            }
            let value = try state(context)
            let scopeKey = value.destinationURL.flatMap { url in
                value.configurationId.map { url + "\n" + $0 }
            } ?? "__unbound__"
            let scoped = try mutations(context).filter {
                $0.url == url && $0.scopeKey == scopeKey
            }
            let deletion = FeedMutation(url: url, scopeKey: scopeKey, kind: "delete",
                                        baseVersion: target.serverVersion,
                                        sequence: value.nextSequence,
                                        localRevision: (target.mutationRevision ?? 0) + 1)
            if let known = scoped.compactMap({ storedSnapshot($0) })
                .max(by: { $0.version < $1.version }) {
                setSnapshot(known, on: deletion)
            } else if scoped.isEmpty {
                // The feed still contains the server baseline before hiding it.
                captureVisibleServerSnapshot(target, on: deletion)
            }
            target.isLocallyDeleted = true
            target.locallyModified = true
            target.mutationRevision = deletion.localRevision
            context.insert(deletion)
            value.nextSequence += 1
        }
    }

    enum Resolution { case keepServer, applyMine, keepRemoved, addToServer, correct, discard }

    enum PreviousProposalAction: Equatable { case transfer, discard }

    func resolvePrevious(opId: String, action: PreviousProposalAction) throws {
        try transaction { context in
            let value = try state(context)
            guard let destinationURL = value.destinationURL,
                  let configurationId = value.configurationId,
                  value.firstReconciliationComplete, !value.suspended,
                  let selected = try mutations(context).first(where: { $0.opId == opId }),
                  selected.scopeKey != destinationURL + "\n" + configurationId,
                  selected.scopeKey != "__unbound__" else { throw StoreError.invalidEdit }
            let related = try mutations(context).filter {
                $0.url == selected.url && $0.scopeKey == selected.scopeKey
            }
            guard !related.contains(where: { $0.sequence < selected.sequence }) else {
                throw StoreError.invalidEdit
            }
            if selected.kind == "upsert", selected.baseVersion == nil,
               let next = related.first(where: { $0.sequence > selected.sequence }),
               next.kind == "upsert", next.baseVersion == nil {
                // Removing the old-scope head promotes a sparse successor to
                // a standalone create. Keep its dirty fields and inherit only
                // the unchanged fields from the complete predecessor.
                next.title = next.title ?? selected.title
                next.isActive = next.isActive ?? selected.isActive
                next.mode = next.mode ?? selected.mode
                next.maxArticles = next.maxArticles ?? selected.maxArticles
            }
            if action == .discard {
                context.delete(selected)
                return
            }
            let target = try feed(selected.url, context)
            let baseVersion = target?.serverVersion
            let full = selected.title != nil && selected.isActive != nil &&
                       selected.mode != nil && selected.maxArticles != nil
            guard selected.kind == "delete" || baseVersion != nil || full else {
                throw StoreError.invalidEdit
            }
            let replacement = FeedMutation(
                url: selected.url,
                scopeKey: destinationURL + "\n" + configurationId,
                kind: selected.kind,
                baseVersion: baseVersion,
                title: selected.title,
                isActive: selected.isActive,
                mode: selected.mode,
                maxArticles: selected.maxArticles,
                sequence: value.nextSequence,
                localRevision: (target?.mutationRevision ?? 0) + 1,
                origin: "explicit_transfer")
            if let target { captureVisibleServerSnapshot(target, on: replacement) }
            value.nextSequence += 1
            if selected.kind == "delete" {
                target?.isLocallyDeleted = true
            } else if let target {
                if let title = selected.title { target.name = title }
                if let active = selected.isActive { target.isEnabled = active }
                if let mode = selected.mode {
                    target.mode = mode == "summarize" ? .briefing : .fidelity
                }
                if let max = selected.maxArticles { target.maxArticles = max }
                target.isLocallyDeleted = false
            } else if let title = selected.title, let active = selected.isActive,
                      let mode = selected.mode, let max = selected.maxArticles {
                context.insert(Domain.Feed(url: selected.url, name: title,
                                           mode: mode == "summarize" ? .briefing : .fidelity,
                                           maxArticles: max, isEnabled: active,
                                           locallyModified: true))
            }
            target?.locallyModified = true
            target?.mutationRevision = replacement.localRevision
            context.insert(replacement)
            context.delete(selected)
        }
    }

    func resolve(opId: String, action: Resolution, correctedTitle: String? = nil) throws {
        try transaction { context in
            let value = try state(context)
            guard let destinationURL = value.destinationURL,
                  let configurationId = value.configurationId,
                  value.firstReconciliationComplete, !value.suspended else {
                throw StoreError.staleBinding
            }
            let activeScope = destinationURL + "\n" + configurationId
            guard let selected = try mutations(context).first(where: { $0.opId == opId }),
                  selected.scopeKey == activeScope,
                  ["needs_resolution", "conflict", "rejected"].contains(selected.status)
            else { throw StoreError.staleBinding }
            let scoped = try mutations(context).filter {
                $0.url == selected.url && $0.scopeKey == activeScope
            }
            guard scoped.first?.opId == selected.opId else { throw StoreError.invalidEdit }
            let target = try feed(selected.url, context)
            let successors = scoped.filter { $0.sequence > selected.sequence }
            let snapshot = storedSnapshot(selected)
            switch action {
            case .keepServer:
                guard let snapshot else { throw StoreError.invalidSnapshot }
                try setVisible(snapshot, context: context, preserveLocalDelete: false)
                context.delete(selected)
                if successors.isEmpty { target?.locallyModified = false }
                if let first = successors.first {
                    first.status = "needs_resolution"
                    setSnapshot(snapshot, on: first)
                }
            case .keepRemoved, .discard:
                guard action != .discard || selected.status == "rejected" else {
                    throw StoreError.invalidEdit
                }
                if action == .keepRemoved && snapshot != nil { throw StoreError.invalidEdit }
                if let snapshot {
                    if action == .discard,
                       snapshot.version < (target?.serverVersion ?? -1) {
                        // Never consume the intent using a stale baseline.
                        throw StoreError.invalidSnapshot
                    }
                    try setVisible(snapshot, context: context, preserveLocalDelete: false)
                } else if action == .discard && selected.baseVersion != nil {
                    // A rejected edit must have its prior server values; never
                    // drop the only proposal while retaining rejected fields.
                    throw StoreError.invalidSnapshot
                } else if successors.isEmpty, action == .discard, let target {
                    context.delete(target)
                } else {
                    target?.isLocallyDeleted = true
                }
                if action == .keepRemoved { target?.isLocallyDeleted = true }
                if let first = successors.first {
                    first.status = "needs_resolution"
                    if let snapshot {
                        setSnapshot(snapshot, on: first)
                    } else if selected.kind == "upsert" {
                        // A rejected/absent create had a complete null-base
                        // payload. Retain its unchanged fields for an explicit
                        // later Add to server decision on the successor.
                        first.title = first.title ?? selected.title
                        first.isActive = first.isActive ?? selected.isActive
                        first.mode = first.mode ?? selected.mode
                        first.maxArticles = first.maxArticles ?? selected.maxArticles
                    }
                } else {
                    target?.locallyModified = false
                }
                context.delete(selected)
            case .applyMine, .addToServer, .correct:
                if action == .applyMine && snapshot == nil { throw StoreError.invalidSnapshot }
                if action == .addToServer && (snapshot != nil || selected.kind != "upsert") {
                    throw StoreError.invalidEdit
                }
                if action == .correct {
                    guard selected.kind == "upsert", selected.status == "rejected",
                          let correctedTitle,
                          !correctedTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    else { throw StoreError.invalidTitle }
                }
                let baseVersion: Int64? = action == .addToServer ? nil :
                    (selected.serverVersion ?? selected.baseVersion)
                let title = correctedTitle ?? selected.title
                if selected.kind == "upsert", baseVersion == nil,
                   (title == nil || selected.isActive == nil ||
                    selected.mode == nil || selected.maxArticles == nil) {
                    throw StoreError.invalidEdit
                }
                let replacement = FeedMutation(
                    url: selected.url, scopeKey: selected.scopeKey,
                    kind: selected.kind,
                    baseVersion: baseVersion,
                    title: title,
                    isActive: selected.isActive, mode: selected.mode,
                    maxArticles: selected.maxArticles,
                    sequence: selected.sequence,
                    localRevision: selected.localRevision + 1,
                    origin: "resolved")
                copySnapshot(selected, to: replacement)
                context.delete(selected)
                context.insert(replacement)
                var visible = target
                if selected.kind == "delete" {
                    visible?.isLocallyDeleted = true
                    visible?.locallyModified = true
                    visible?.mutationRevision = max(visible?.mutationRevision ?? 0,
                                                   replacement.localRevision)
                } else {
                    if visible == nil {
                        guard let title, let mode = selected.mode,
                              let active = selected.isActive,
                              let max = selected.maxArticles else { throw StoreError.invalidEdit }
                        let created = Domain.Feed(url: selected.url, name: title,
                                              mode: mode == "summarize" ? .briefing : .fidelity,
                                              maxArticles: max, isEnabled: active,
                                              locallyModified: true,
                                              serverId: snapshot?.id,
                                              serverVersion: snapshot?.version)
                        context.insert(created)
                        visible = created
                    }
                    if let visible {
                        if let title { visible.name = title }
                        if let active = selected.isActive { visible.isEnabled = active }
                        if let mode = selected.mode {
                            visible.mode = mode == "summarize" ? .briefing : .fidelity
                        }
                        if let max = selected.maxArticles { visible.maxArticles = max }
                        visible.isLocallyDeleted = false
                        visible.locallyModified = true
                        visible.mutationRevision = max(visible.mutationRevision ?? 0,
                                                       replacement.localRevision)
                    }
                }
                // The resolved head is older than any queued local edits, even
                // when that head is a delete. Rebuild their visible state in
                // order without changing the queued payloads.
                if let visible {
                    for successor in successors {
                        if successor.kind == "delete" {
                            visible.isLocallyDeleted = true
                        } else {
                            if let title = successor.title { visible.name = title }
                            if let active = successor.isActive { visible.isEnabled = active }
                            if let mode = successor.mode {
                                visible.mode = mode == "summarize" ? .briefing : .fidelity
                            }
                            if let maximum = successor.maxArticles {
                                visible.maxArticles = maximum
                            }
                            visible.isLocallyDeleted = false
                        }
                        visible.mutationRevision = max(visible.mutationRevision ?? 0,
                                                       successor.localRevision)
                    }
                }
            }
        }
    }

    enum StoreError: LocalizedError {
        case busy, staleBinding, staleSentRevision, invalidSnapshot, invalidEdit
        case invalidURL, invalidTitle, injectedSaveFailure

        var errorDescription: String? {
            switch self {
            case .invalidURL: return "Enter an http or https feed URL."
            case .invalidTitle: return "Enter a feed title."
            case .invalidEdit: return "This feed change needs a complete valid proposal."
            case .staleBinding: return "This feed belongs to a previous server. Review its saved proposal."
            default: return "The feed change could not be saved."
            }
        }
    }
}

final class IOSFeedV2StorePortAdapter: NSObject, FeedV2StorePort {
    let engine: IOSFeedV2StoreEngine

    @MainActor init(container: ModelContainer) {
        self.engine = IOSFeedV2StoreEngine(container: container)
    }

    private func respond<T: AnyObject>(
        _ operation: @escaping @MainActor () throws -> T?,
        completionHandler: @escaping (FeedV2StoreResult<T>?, Error?) -> Void
    ) {
        Task { @MainActor in
            do { completionHandler(FeedV2StoreResultSuccess(value: try operation()), nil) }
            catch let error as IOSFeedV2StoreEngine.StoreError {
                let result: FeedV2StoreResult<KotlinNothing>
                switch error {
                case .busy: result = FeedV2StoreResultBusy()
                case .staleBinding: result = FeedV2StoreResultStaleBinding()
                case .staleSentRevision: result = FeedV2StoreResultStaleSentRevision()
                default: result = FeedV2StoreResultFailure(message: String(describing: error))
                }
                completionHandler(unsafeBitCast(result, to: FeedV2StoreResult<T>.self), nil)
            } catch {
                let result: FeedV2StoreResult<KotlinNothing> =
                    FeedV2StoreResultFailure(message: error.localizedDescription)
                completionHandler(unsafeBitCast(result, to: FeedV2StoreResult<T>.self), nil)
            }
        }
    }

    func beginSyncRun(destination: FeedV2Destination,
                      completionHandler: @escaping (FeedV2StoreResult<FeedV2RunToken>?, Error?) -> Void) {
        respond({ try self.engine.begin(destination) }, completionHandler: completionHandler)
    }

    func endSyncRun(token: FeedV2RunToken, completionHandler: @escaping (Error?) -> Void) {
        Task { @MainActor in self.engine.end(token); completionHandler(nil) }
    }

    func getServerIdentity(token: FeedV2RunToken,
                           completionHandler: @escaping (FeedV2StoreResult<FeedV2Binding>?, Error?) -> Void) {
        respond({ try self.engine.identity(token) }, completionHandler: completionHandler)
    }

    func suspendBinding(token: FeedV2RunToken, binding: FeedV2Binding, reason: String,
                        completionHandler: @escaping (FeedV2StoreResult<KotlinUnit>?, Error?) -> Void) {
        respond({ try self.engine.suspend(token, binding); return KotlinUnit() }, completionHandler: completionHandler)
    }

    func reconcileAndBindFullSnapshot(token: FeedV2RunToken, destination: FeedV2Destination,
                                      snapshot: FeedChangesV2Response,
                                      completionHandler: @escaping (FeedV2StoreResult<FeedV2Binding>?, Error?) -> Void) {
        respond({ try self.engine.reconcile(token, destination: destination, snapshot: snapshot) },
                completionHandler: completionHandler)
    }

    func loadPendingMutations(token: FeedV2RunToken, binding: FeedV2Binding, maxItems: Int32,
                              completionHandler: @escaping (FeedV2StoreResult<NSArray>?, Error?) -> Void) {
        respond({ try self.engine.claim(token, binding, maxItems: maxItems) as NSArray }, completionHandler: completionHandler)
    }

    func pendingSummary(token: FeedV2RunToken, binding: FeedV2Binding,
                        completionHandler: @escaping (FeedV2StoreResult<FeedV2WorkSummary>?, Error?) -> Void) {
        respond({ try self.engine.summary(token, binding) }, completionHandler: completionHandler)
    }

    func acknowledge(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
                     sentRevision: Int64, current: FeedSnapshotV2?,
                     completionHandler: @escaping (FeedV2StoreResult<KotlinUnit>?, Error?) -> Void) {
        respond({ try self.engine.acknowledge(token, binding, opId: opId,
                                              revision: sentRevision, current: current)
                  return KotlinUnit() }, completionHandler: completionHandler)
    }

    func recordConflict(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
                        sentRevision: Int64, current: FeedSnapshotV2,
                        completionHandler: @escaping (FeedV2StoreResult<KotlinUnit>?, Error?) -> Void) {
        respond({ try self.engine.conflict(token, binding, opId: opId,
                                           revision: sentRevision, current: current)
                  return KotlinUnit() }, completionHandler: completionHandler)
    }

    func recordRejection(token: FeedV2RunToken, binding: FeedV2Binding, opId: String,
                         sentRevision: Int64, code: String, message: String?,
                         completionHandler: @escaping (FeedV2StoreResult<KotlinUnit>?, Error?) -> Void) {
        respond({ try self.engine.reject(token, binding, opId: opId,
                                         revision: sentRevision, code: code, message: message)
                  return KotlinUnit() }, completionHandler: completionHandler)
    }

    func applyServerChangesAndCursor(token: FeedV2RunToken, binding: FeedV2Binding,
                                     changes: FeedChangesV2Response,
                                     completionHandler: @escaping (FeedV2StoreResult<KotlinUnit>?, Error?) -> Void) {
        respond({ try self.engine.apply(token, binding, changes: changes)
                  return KotlinUnit() }, completionHandler: completionHandler)
    }
}
