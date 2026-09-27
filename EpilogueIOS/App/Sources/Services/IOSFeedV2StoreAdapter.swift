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

    func destination(for rawURL: String) throws -> FeedV2Destination {
        let normalized = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !normalized.isEmpty else { throw StoreError.invalidEdit }
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
            for mutation in oldMutations where mutation.scopeKey == "__unbound__" {
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
                } else if mutation.kind == "delete" {
                    // A never-seen delete can be acknowledged locally after binding.
                    context.delete(mutation)
                }
            }
            for row in snapshot.changes where !row.url.hasPrefix("synthetic://") {
                try setVisible(row, context: context, preserveLocalDelete: false)
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
                } else if let current, !next.sent {
                    next.baseVersion = current.version
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
                        target.isLocallyDeleted = next.kind == "delete"
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
                if let head = related.first, head.status == "pending", !head.sent,
                   row.version > (head.baseVersion ?? -1) {
                    head.status = "needs_resolution"
                    setSnapshot(row, on: head)
                } else if let head = related.first, head.status != "pending" {
                    setSnapshot(row, on: head)
                }
                try setVisible(row, context: context,
                               preserveLocalDelete: related.first?.kind == "delete")
            }
            value.cursorVersion = changes.serverVersion
        }
    }

    func edit(url: String, title: String, mode: Domain.ProcessingMode,
              isEnabled: Bool, maxArticles: Int) throws {
        guard !url.isEmpty, !url.hasPrefix("synthetic://"), maxArticles >= 0 else {
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
                existing.mutationRevision = (existing.mutationRevision ?? 0) + 1
            }
            let revision = existing?.mutationRevision ?? 0
            let scopeKey = value.destinationURL.flatMap { url in
                value.configurationId.map { url + "\n" + $0 }
            } ?? "__unbound__"
            let full = existing == nil || originalVersion == nil
            context.insert(FeedMutation(
                url: url, scopeKey: scopeKey, kind: "upsert",
                baseVersion: originalVersion,
                title: full || changedTitle ? title : nil,
                isActive: full || changedEnabled ? isEnabled : nil,
                mode: full || changedMode ? (mode == .briefing ? "summarize" : "raw") : nil,
                maxArticles: full || changedCap ? maxArticles : nil,
                sequence: value.nextSequence, localRevision: revision))
            value.nextSequence += 1
        }
    }

    func delete(url: String) throws {
        try transaction { context in
            guard let target = try feed(url, context), !url.hasPrefix("synthetic://") else {
                throw StoreError.invalidEdit
            }
            let value = try state(context)
            target.isLocallyDeleted = true
            target.locallyModified = true
            target.mutationRevision = (target.mutationRevision ?? 0) + 1
            let scopeKey = value.destinationURL.flatMap { url in
                value.configurationId.map { url + "\n" + $0 }
            } ?? "__unbound__"
            context.insert(FeedMutation(url: url, scopeKey: scopeKey, kind: "delete",
                                        baseVersion: target.serverVersion,
                                        sequence: value.nextSequence,
                                        localRevision: target.mutationRevision ?? 0))
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
            let preceding = try mutations(context).contains {
                $0.url == selected.url && $0.scopeKey == selected.scopeKey &&
                $0.sequence < selected.sequence
            }
            guard !preceding else { throw StoreError.invalidEdit }
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
            guard let selected = try mutations(context).first(where: { $0.opId == opId }),
                  ["needs_resolution", "conflict", "rejected"].contains(selected.status)
            else { throw StoreError.invalidEdit }
            let target = try feed(selected.url, context)
            let successors = try mutations(context).filter {
                $0.url == selected.url && $0.sequence > selected.sequence
            }
            switch action {
            case .keepServer, .keepRemoved, .discard:
                context.delete(selected)
                if successors.isEmpty { target?.locallyModified = false }
                if action == .keepRemoved {
                    target?.isLocallyDeleted = true
                } else if selected.kind == "delete" {
                    target?.isLocallyDeleted = false
                }
                if let first = successors.first { first.status = "needs_resolution" }
            case .applyMine, .addToServer, .correct:
                let mode = selected.mode
                let replacement = FeedMutation(
                    url: selected.url, scopeKey: selected.scopeKey,
                    kind: selected.kind,
                    baseVersion: action == .addToServer ? nil : selected.serverVersion,
                    title: correctedTitle ?? selected.title,
                    isActive: selected.isActive, mode: mode,
                    maxArticles: selected.maxArticles,
                    sequence: selected.sequence,
                    localRevision: selected.localRevision + 1,
                    origin: "resolved")
                context.delete(selected)
                context.insert(replacement)
                target?.mutationRevision = max(target?.mutationRevision ?? 0, replacement.localRevision)
            }
            _ = value
        }
    }

    enum StoreError: Error {
        case busy, staleBinding, staleSentRevision, invalidSnapshot, invalidEdit, injectedSaveFailure
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
