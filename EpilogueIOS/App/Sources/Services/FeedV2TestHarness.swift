#if DEBUG
import Foundation
import SwiftData
import Domain
import Data
import EpilogueShared

/// Keeps test-side KMP construction in the app image. Linking the static KMP
/// framework into a hosted XCTest bundle a second time corrupts ObjC bridging.
@MainActor
final class FeedV2TestHarness {
    enum Failure: Error { case assertion(String) }
    private let model: ModelContainer
    private let adapter: IOSFeedV2StorePortAdapter
    private let feedURL = "https://example.test/feed.xml"
    private let instance = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    static func seedUIFixture(context: ModelContext) {
        do {
            for row in try context.fetch(FetchDescriptor<Domain.Feed>()) { context.delete(row) }
            for row in try context.fetch(FetchDescriptor<FeedMutation>()) { context.delete(row) }
            for row in try context.fetch(FetchDescriptor<FeedSyncState>()) { context.delete(row) }
            let scope = "https://server.test\nfeed-ui-fixture"
            context.insert(FeedSyncState(destinationURL: "https://server.test",
                                         configurationId: "feed-ui-fixture",
                                         serverInstanceId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                                         cursorVersion: 8, firstReconciliationComplete: true))
            let examples: [(String, String, String, String?, Bool)] = [
                ("conflict", "Web headline", "conflict", "My headline", false),
                ("rejected", "Rejected feed", "rejected", "Bad request", false),
                ("absent", "Missing feed", "needs_resolution", "Missing feed", true),
                ("delete", "Removed locally", "conflict", nil, true),
                ("rejected-delete", "Rejected removal", "rejected", nil, true)
            ]
            for (index, example) in examples.enumerated() {
                let url = "https://example.test/\(example.0).xml"
                context.insert(Domain.Feed(url: url, name: example.1, mode: .fidelity,
                                           serverId: example.0 == "absent" ? nil : UUID().uuidString.lowercased(),
                                           serverVersion: example.0 == "absent" ? nil : 8,
                                           isLocallyDeleted: example.4))
                let mutation = FeedMutation(url: url, scopeKey: scope,
                                            kind: example.0.contains("delete") ? "delete" : "upsert",
                                            baseVersion: 7, title: example.3,
                                            isActive: true, mode: "raw", maxArticles: 5,
                                            sequence: Int64(index + 1), localRevision: 1,
                                            status: example.2, sent: true)
                if example.0 != "absent" {
                    mutation.serverKind = "feed"
                    mutation.serverTitle = example.1
                    mutation.serverIsActive = true
                    mutation.serverMode = "raw"
                    mutation.serverMaxArticles = 5
                    mutation.serverVersion = 8
                }
                if example.0 == "rejected" {
                    mutation.rejectionCode = "invalid_fields"
                    mutation.rejectionMessage = "The title needs correction."
                } else if example.0 == "rejected-delete" {
                    mutation.rejectionCode = "delete_denied"
                    mutation.rejectionMessage = "The server rejected this removal."
                }
                context.insert(mutation)
            }
            try context.save()
        } catch {
            context.rollback()
            assertionFailure("Feed UI fixture failed: \(error)")
        }
    }

    init(_ model: ModelContainer) {
        self.model = model
        self.adapter = IOSFeedV2StorePortAdapter(container: model)
    }

    private func check(_ value: Bool, _ message: String) throws {
        if !value { throw Failure.assertion(message) }
    }

    private func row(_ version: Int64, _ title: String = "Server") -> FeedSnapshotV2 {
        FeedSnapshotV2(kind: "feed", id: instance, url: feedURL, version: version,
                       title: title, isActive: KotlinBoolean(bool: true), mode: "raw",
                       maxArticles: KotlinInt(int: 5))
    }

    private func changes(_ version: Int64, _ rows: [FeedSnapshotV2]) -> FeedChangesV2Response {
        FeedChangesV2Response(serverInstanceId: instance, serverVersion: version, changes: rows)
    }

    private func bind(_ withRow: Bool = true) throws -> (FeedV2Destination, FeedV2RunToken, FeedV2Binding) {
        let destination = try adapter.engine.destination(for: "https://server.test")
        let token = try adapter.engine.begin(destination)
        let binding = try adapter.engine.reconcile(token, destination: destination,
                                                   snapshot: changes(withRow ? 4 : 0,
                                                                     withRow ? [row(4)] : []))
        return (destination, token, binding)
    }

    func offlineDeleteAndReopenAssertion() async throws {
        let (_, token, _) = try bind()
        adapter.engine.end(token)
        try adapter.engine.delete(url: feedURL)
        let repository = FeedRepository(modelContext: ModelContext(model))
        let enabled = try await repository.getEnabledFeeds()
        try check(enabled.isEmpty, "Hidden offline delete leaked into generation")
        let context = ModelContext(model)
        let mutation = try context.fetch(FetchDescriptor<FeedMutation>()).first
        try check(mutation?.kind == "delete" && mutation?.baseVersion == 4,
                  "Offline delete was not durable")
    }

    func replayAndSuccessorAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Mine", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.edit(url: feedURL, title: "Later", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        try adapter.engine.apply(token, binding, changes: changes(5, [row(5, "Mine")]))
        let replay = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try check(replay.opId == sent.opId &&
                  replay.payload.baseVersion?.int64Value == sent.payload.baseVersion?.int64Value,
                  "Lost-ACK replay changed its immutable payload")
        try adapter.engine.acknowledge(token, binding, opId: sent.opId,
                                       revision: sent.sentRevision, current: row(5, "Mine"))
        let context = ModelContext(model)
        let feed = try context.fetch(FetchDescriptor<Domain.Feed>()).first
        let next = try context.fetch(FetchDescriptor<FeedMutation>()).first
        try check(feed?.name == "Later" && next?.baseVersion == 5 && next?.status == "pending",
                  "Acknowledgement erased or blocked the successor")
        adapter.engine.end(token)
    }

    func newerServerWinsWithProposalAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Mine", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        try adapter.engine.apply(token, binding, changes: changes(5, [row(5, "Web")]))
        let context = ModelContext(model)
        let feed = try context.fetch(FetchDescriptor<Domain.Feed>()).first
        let proposal = try context.fetch(FetchDescriptor<FeedMutation>()).first
        try check(feed?.name == "Web" && feed?.serverVersion == 5 &&
                  proposal?.title == "Mine" && proposal?.status == "needs_resolution" &&
                  proposal?.serverTitle == "Web",
                  "Newer server state or local proposal was lost")
        adapter.engine.end(token)
    }

    func newerPullRefreshesConflictAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Mine", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.conflict(token, binding, opId: sent.opId,
                                    revision: sent.sentRevision, current: row(5, "Web v5"))
        try adapter.engine.apply(token, binding, changes: changes(6, [row(6, "Web v6")]))
        let context = ModelContext(model)
        let proposal = try context.fetch(FetchDescriptor<FeedMutation>()).first
        try check(proposal?.serverVersion == 6 && proposal?.serverTitle == "Web v6" &&
                  proposal?.title == "Mine", "Newer pull lost conflict snapshot or proposal")
        try adapter.engine.resolve(opId: sent.opId, action: .keepServer)
        let resolved = try ModelContext(model).fetch(FetchDescriptor<Domain.Feed>()).first
        try check(resolved?.serverVersion == 6 && resolved?.name == "Web v6",
                  "Keep server restored an older conflict snapshot")
        adapter.engine.end(token)
    }

    func legacyHeadThenPrebindEditAssertion() throws {
        let context = ModelContext(model)
        context.insert(Domain.Feed(url: feedURL, name: "Local B", mode: .fidelity))
        context.insert(FeedMutation(url: feedURL, scopeKey: "__unbound__", kind: "upsert",
                                    title: "Server A", isActive: true, mode: "raw",
                                    maxArticles: 5, sequence: 1, localRevision: 0,
                                    status: "needs_reconciliation", origin: "legacy"))
        context.insert(FeedMutation(url: feedURL, scopeKey: "__unbound__", kind: "upsert",
                                    title: "Local B", isActive: true, mode: "raw",
                                    maxArticles: 5, sequence: 2, localRevision: 1))
        try context.save()
        let destination = try adapter.engine.destination(for: "https://server.test")
        let token = try adapter.engine.begin(destination)
        let binding = try adapter.engine.reconcile(
            token, destination: destination,
            snapshot: changes(4, [row(4, "Server A")]))
        let rows = try ModelContext(model).fetch(FetchDescriptor<FeedMutation>())
        let claim = try adapter.engine.claim(token, binding, maxItems: 10)
        try check(rows.count == 1 && rows[0].title == "Local B" &&
                  rows[0].status == "needs_resolution" && rows[0].serverVersion == 4 &&
                  claim.isEmpty,
                  "Prebind successor was sent as a null-base create against an existing URL")
        adapter.engine.end(token)
    }

    func prebindingDeleteStaysHiddenAssertion() async throws {
        let context = ModelContext(model)
        context.insert(Domain.Feed(url: feedURL, name: "Local", mode: .fidelity,
                                   isLocallyDeleted: true))
        context.insert(FeedMutation(url: feedURL, scopeKey: "__unbound__", kind: "delete",
                                    sequence: 1, localRevision: 1))
        try context.save()
        let (_, token, _) = try bind()
        let reopened = ModelContext(model)
        let feed = try reopened.fetch(FetchDescriptor<Domain.Feed>()).first
        let mutation = try reopened.fetch(FetchDescriptor<FeedMutation>()).first
        let enabled = try await FeedRepository(modelContext: reopened).getEnabledFeeds()
        try check(feed?.isLocallyDeleted == true && enabled.isEmpty &&
                  mutation?.status == "needs_resolution" && mutation?.serverVersion == 4,
                  "First reconciliation exposed a pending local delete")
        adapter.engine.end(token)
    }

    func rejectedCreateDiscardAssertion() throws {
        let (_, token, binding) = try bind(false)
        try adapter.engine.edit(url: feedURL, title: "Invalid create", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: sent.opId,
                                  revision: sent.sentRevision, code: "invalid_fields", message: nil)
        try adapter.engine.resolve(opId: sent.opId, action: .discard)
        let reopened = ModelContext(model)
        let feeds = try reopened.fetch(FetchDescriptor<Domain.Feed>())
        let mutations = try reopened.fetch(FetchDescriptor<FeedMutation>())
        try check(feeds.isEmpty && mutations.isEmpty,
                  "Discarding a rejected create left an active unsynced feed")
        adapter.engine.end(token)
    }

    func rejectedEditDiscardAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Rejected local", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: sent.opId,
                                  revision: sent.sentRevision, code: "invalid_fields", message: nil)
        try adapter.engine.resolve(opId: sent.opId, action: .discard)
        let reopened = ModelContext(model)
        let feed = try reopened.fetch(FetchDescriptor<Domain.Feed>()).first
        let mutations = try reopened.fetch(FetchDescriptor<FeedMutation>())
        try check(feed?.name == "Server" && feed?.serverVersion == 4 &&
                  mutations.isEmpty,
                  "Discarding rejected edit kept local values or outbox state")
        adapter.engine.end(token)
    }

    func rejectedDeleteDiscardAssertion() async throws {
        let (_, token, binding) = try bind()
        try adapter.engine.delete(url: feedURL)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: sent.opId,
                                  revision: sent.sentRevision, code: "invalid_fields", message: nil)
        let stored = try require(ModelContext(model).fetch(FetchDescriptor<FeedMutation>()).first)
        try check(stored.serverKind == "feed" && stored.serverVersion == 4 &&
                  stored.serverTitle == "Server", "Delete did not retain server baseline")
        try adapter.engine.resolve(opId: sent.opId, action: .discard)
        let reopened = ModelContext(model)
        let feed = try require(reopened.fetch(FetchDescriptor<Domain.Feed>()).first)
        let enabled = try await FeedRepository(modelContext: reopened).getEnabledFeeds()
        try check(feed.name == "Server" && feed.serverVersion == 4 &&
                  feed.isLocallyDeleted != true && enabled.map(\.url) == [feedURL] &&
                  reopened.fetch(FetchDescriptor<FeedMutation>()).isEmpty,
                  "Discarding rejected delete failed to restore the server feed")
        adapter.engine.end(token)
    }

    func rejectedDeleteDiscardKeepsNewerSnapshotAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.delete(url: feedURL)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: sent.opId,
                                  revision: sent.sentRevision, code: "invalid_fields", message: nil)
        try adapter.engine.apply(token, binding, changes: changes(5, [row(5, "Newer web")]))
        try adapter.engine.resolve(opId: sent.opId, action: .discard)
        let reopened = ModelContext(model)
        let feed = try require(reopened.fetch(FetchDescriptor<Domain.Feed>()).first)
        let pending = try reopened.fetch(FetchDescriptor<FeedMutation>())
        try check(feed.name == "Newer web" && feed.serverVersion == 5 &&
                  feed.isLocallyDeleted != true && pending.isEmpty,
                  "Discarding rejected delete lost newer known server state")
        adapter.engine.end(token)
    }

    func rejectedDeleteSuccessorDiscardAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Accepted edit", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let edit = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.delete(url: feedURL)
        try adapter.engine.acknowledge(token, binding, opId: edit.opId,
                                       revision: edit.sentRevision, current: row(5, "Accepted edit"))
        let deletion = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: deletion.opId,
                                  revision: deletion.sentRevision, code: "invalid_fields", message: nil)
        try adapter.engine.resolve(opId: deletion.opId, action: .discard)
        let reopened = ModelContext(model)
        let feed = try require(reopened.fetch(FetchDescriptor<Domain.Feed>()).first)
        let pending = try reopened.fetch(FetchDescriptor<FeedMutation>())
        try check(feed.name == "Accepted edit" && feed.serverVersion == 5 &&
                  feed.isLocallyDeleted != true && pending.isEmpty,
                  "Discarding successor delete lost the acknowledged server baseline")
        adapter.engine.end(token)
    }

    func keepServerSuccessorSnapshotAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "First", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.edit(url: feedURL, title: "Later", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        try adapter.engine.conflict(token, binding, opId: sent.opId,
                                    revision: sent.sentRevision, current: row(5, "Web"))
        try adapter.engine.resolve(opId: sent.opId, action: .keepServer)
        let reopened = ModelContext(model)
        let next = try require(reopened.fetch(FetchDescriptor<FeedMutation>()).first)
        try check(next.status == "needs_resolution" && next.serverKind == "feed" &&
                  next.serverVersion == 5 && next.serverTitle == "Web",
                  "Blocked successor lost known server snapshot")
        try adapter.engine.resolve(opId: next.opId, action: .applyMine)
        let replacement = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try check(replacement.payload.baseVersion?.int64Value == 5 &&
                  replacement.payload.fields?.title == "Later",
                  "Explicit successor resolution produced an invalid null-base edit")
        adapter.engine.end(token)
    }

    func correctedRejectedEditKeepsBaseAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Bad", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.reject(token, binding, opId: sent.opId,
                                  revision: sent.sentRevision, code: "invalid_fields", message: nil)
        try adapter.engine.resolve(opId: sent.opId, action: .correct,
                                   correctedTitle: "Corrected")
        let replacement = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try check(replacement.opId != sent.opId &&
                  replacement.payload.baseVersion?.int64Value == 4 &&
                  replacement.payload.fields?.title == "Corrected",
                  "Corrected rejected edit lost its sendable server base")
        adapter.engine.end(token)
    }

    func resolutionScopeAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Mine", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.conflict(token, binding, opId: sent.opId,
                                    revision: sent.sentRevision, current: row(5, "Web"))
        adapter.engine.end(token)
        try adapter.engine.startNewBinding()
        do {
            try adapter.engine.resolve(opId: sent.opId, action: .keepServer)
            throw Failure.assertion("Old scope resolved after server replacement")
        } catch IOSFeedV2StoreEngine.StoreError.staleBinding {}
        let reopened = ModelContext(model)
        let old = try require(reopened.fetch(FetchDescriptor<FeedMutation>()).first)
        try check(old.opId == sent.opId && old.status == "conflict",
                  "Stale resolution changed old-scope proposal")
    }

    func resolutionIgnoresOtherScopeSuccessorsAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "Mine", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.conflict(token, binding, opId: sent.opId,
                                    revision: sent.sentRevision, current: row(5, "Web"))
        let context = ModelContext(model)
        let other = FeedMutation(url: feedURL, scopeKey: "https://old.test\nold-config",
                                 kind: "upsert", title: "Previous server proposal",
                                 sequence: 999, localRevision: 1)
        context.insert(other)
        try context.save()
        try adapter.engine.resolve(opId: sent.opId, action: .keepServer)
        let reopened = ModelContext(model)
        let remaining = try require(reopened.fetch(FetchDescriptor<FeedMutation>()).first)
        try check(remaining.opId == other.opId && remaining.status == "pending" &&
                  remaining.serverVersion == nil,
                  "Resolving this server changed a previous-scope proposal")
        adapter.engine.end(token)
    }

    func invalidInputRollsBackAssertion() throws {
        for (url, title) in [("example.test/feed.xml", "Name"),
                             ("https://example.test/feed.xml", "   ")] {
            do {
                try adapter.engine.edit(url: url, title: title, mode: .fidelity,
                                        isEnabled: true, maxArticles: 5)
                throw Failure.assertion("Invalid feed input was accepted")
            } catch IOSFeedV2StoreEngine.StoreError.invalidURL where !url.hasPrefix("https://") {
            } catch IOSFeedV2StoreEngine.StoreError.invalidTitle where url.hasPrefix("https://") {
            }
        }
        let reopened = ModelContext(model)
        let feeds = try reopened.fetch(FetchDescriptor<Domain.Feed>())
        let mutations = try reopened.fetch(FetchDescriptor<FeedMutation>())
        try check(feeds.isEmpty && mutations.isEmpty,
                  "Invalid edit persisted a feed or mutation")
    }

    func cursorFailureAssertion() throws {
        let (_, token, binding) = try bind()
        adapter.engine.failNextSaveForTesting = true
        do {
            try adapter.engine.apply(token, binding, changes: changes(5, [row(5)]))
            throw Failure.assertion("Injected cursor save unexpectedly succeeded")
        } catch IOSFeedV2StoreEngine.StoreError.injectedSaveFailure {}
        let context = ModelContext(model)
        try check(try context.fetch(FetchDescriptor<FeedSyncState>()).first?.cursorVersion == 4 &&
                  context.fetch(FetchDescriptor<Domain.Feed>()).first?.serverVersion == 4,
                  "Cursor and row did not roll back together")
        adapter.engine.end(token)
    }

    func bindingScopeAssertion() throws {
        let (destination, token, binding) = try bind()
        let localOnly = Domain.Feed(url: "synthetic://local", name: "Local source", mode: .fidelity)
        let seedContext = ModelContext(model)
        seedContext.insert(localOnly)
        try seedContext.save()
        try adapter.engine.edit(url: feedURL, title: "Old", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let oldOnlyURL = "https://example.test/old-only.xml"
        try adapter.engine.edit(url: oldOnlyURL, title: "Old-only proposal",
                                mode: .fidelity, isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        adapter.engine.end(token)
        try adapter.engine.startNewBinding()
        let fresh = try adapter.engine.destination(for: destination.normalizedBaseUrl)
        try check(fresh.configurationId != destination.configurationId,
                  "Same-URL replacement reused the old configuration scope")
        let nextToken = try adapter.engine.begin(fresh)
        let nextBinding = try adapter.engine.reconcile(nextToken, destination: fresh,
                                                       snapshot: changes(0, []))
        try check(try adapter.engine.claim(nextToken, nextBinding, maxItems: 10).isEmpty,
                  "Old sent operation replayed to replacement instance")
        let context = ModelContext(model)
        let mutation = try context.fetch(FetchDescriptor<FeedMutation>()).first {
            $0.opId == sent.opId
        }
        let feed = try context.fetch(FetchDescriptor<Domain.Feed>()).first {
            $0.url == feedURL
        }
        try check(mutation?.opId == sent.opId && feed?.isLocallyDeleted == true,
                  "Old proposal was lost or old feed remained enabled")
        let synthetic = try context.fetch(FetchDescriptor<Domain.Feed>()).first {
            $0.url == "synthetic://local"
        }
        try check(synthetic?.isLocallyDeleted != true,
                  "Replacing a server binding hid a synthetic local-only feed")
        let oldOnly = try context.fetch(FetchDescriptor<Domain.Feed>()).first {
            $0.url == oldOnlyURL
        }
        try check(oldOnly?.isLocallyDeleted == true,
                  "Replacing a server binding exposed an old-scope unacknowledged create")
        adapter.engine.end(nextToken)
    }

    func replacementSlotAssertion() throws {
        let (_, token, binding) = try bind()
        try adapter.engine.edit(url: feedURL, title: "First", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let sent = try require(adapter.engine.claim(token, binding, maxItems: 10).first)
        try adapter.engine.edit(url: feedURL, title: "Second", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        try adapter.engine.apply(token, binding, changes: changes(6, [row(6, "Newer")]))
        try adapter.engine.conflict(token, binding, opId: sent.opId,
                                    revision: sent.sentRevision, current: row(5, "Older"))
        try check(try ModelContext(model).fetch(FetchDescriptor<Domain.Feed>()).first?.serverVersion == 6,
                  "Stale conflict receipt rolled server snapshot back")
        try adapter.engine.resolve(opId: sent.opId, action: .applyMine)
        let ordered = try ModelContext(model).fetch(FetchDescriptor<FeedMutation>())
            .sorted { $0.sequence < $1.sequence }
        try check(ordered.count == 2 && ordered[0].opId != sent.opId &&
                  ordered[0].sequence < ordered[1].sequence,
                  "Resolved operation did not retain the head queue slot")
        try check(try adapter.engine.claim(token, binding, maxItems: 10).map(\.opId) == [ordered[0].opId],
                  "Blocked successor was sent before replacement head")
        adapter.engine.end(token)
    }

    func exportedUseCaseAssertion(_ conflict: Bool) async throws {
        let destination = try adapter.engine.destination(for: "https://server.test")
        try adapter.engine.edit(url: feedURL, title: "Local", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        let remote = FakeRemote(instance: instance, feedURL: feedURL,
                                result: conflict ? .conflict : .applied)
        let useCase = FeedSyncV2UseCase(configuration: FixedConfiguration(destination),
                                       store: adapter, remote: remote)
        let outcome = try await useCase.sync()
        try check(conflict ? outcome is FeedSyncV2Outcome.Partial :
                  outcome is FeedSyncV2Outcome.Complete,
                  "Exported KMP use case returned wrong outcome")
        let mutation = try ModelContext(model).fetch(FetchDescriptor<FeedMutation>()).first
        try check(conflict ? mutation?.status == "conflict" : mutation == nil,
                  "Exported receipt was not committed through SwiftData port")
        let token = try adapter.engine.begin(destination)
        adapter.engine.end(token)
    }

    func initialDeleteUseCaseAssertion() async throws {
        let destination = try adapter.engine.destination(for: "https://server.test")
        try adapter.engine.edit(url: feedURL, title: "Local", mode: .fidelity,
                                isEnabled: true, maxArticles: 5)
        try adapter.engine.delete(url: feedURL)
        let remote = FakeRemote(instance: instance, feedURL: feedURL, result: .applied)
        let useCase = FeedSyncV2UseCase(configuration: FixedConfiguration(destination),
                                       store: adapter, remote: remote)
        let outcome = try await useCase.sync()
        let context = ModelContext(model)
        let feed = try require(context.fetch(FetchDescriptor<Domain.Feed>()).first)
        try check(outcome is FeedSyncV2Outcome.Complete && remote.postCount == 0 &&
                  context.fetch(FetchDescriptor<FeedMutation>()).isEmpty &&
                  feed.isLocallyDeleted == true,
                  "A deleted initial create reached the exported KMP transport or reappeared")
    }

    func cancellationAssertion() async throws {
        let destination = try adapter.engine.destination(for: "https://server.test")
        let remote = FakeRemote(instance: instance, feedURL: feedURL, result: .applied)
        remote.suspendFull = true
        let useCase = FeedSyncV2UseCase(configuration: FixedConfiguration(destination),
                                       store: adapter, remote: remote)
        let bridge = SharedFeedV2Bridge(settings: SettingsRepository(), container: model)
        let task = Task { try await bridge.run(useCase: useCase) }
        for _ in 0..<100 where !remote.fullStarted {
            try await Task.sleep(for: .milliseconds(10))
        }
        try check(remote.fullStarted, "Fake transport never suspended")
        task.cancel()
        remote.releaseFull()
        do {
            _ = try await task.value
            throw Failure.assertion("Cancelled Swift caller reported Complete")
        } catch is CancellationError {}
        let token = try adapter.engine.begin(destination)
        adapter.engine.end(token)
    }

    private func require<T>(_ value: T?) throws -> T {
        guard let value else { throw Failure.assertion("Expected persisted value") }
        return value
    }
}

private final class FixedConfiguration: NSObject, FeedV2ConfigurationPort {
    let destination: FeedV2Destination
    init(_ destination: FeedV2Destination) { self.destination = destination }
    func currentDestination(completionHandler: @escaping (FeedV2Destination?, Error?) -> Void) {
        completionHandler(destination, nil)
    }
}

private final class FakeRemote: NSObject, FeedV2RemotePort {
    enum Result { case applied, conflict }
    let instance: String
    let feedURL: String
    let result: Result
    var suspendFull = false
    var fullStarted = false
    var postCount = 0
    private var pendingFull: (() -> Void)?
    init(instance: String, feedURL: String, result: Result) {
        self.instance = instance
        self.feedURL = feedURL
        self.result = result
    }
    func getFeedChangesV2(destination: FeedV2Destination, sinceVersion: KotlinLong?,
                          serverInstanceId: String?,
                          completionHandler: @escaping (FeedV2RemoteResult<FeedChangesV2Response>?, Error?) -> Void) {
        let response = FeedChangesV2Response(serverInstanceId: instance,
                                              serverVersion: sinceVersion == nil ? 0 : 1,
                                              changes: [])
        let complete = { completionHandler(FeedV2RemoteResultSuccess(value: response), nil) }
        if sinceVersion == nil && suspendFull {
            pendingFull = complete
            fullStarted = true
        } else { complete() }
    }
    func releaseFull() { pendingFull?(); pendingFull = nil }
    func postFeedMutationsV2(destination: FeedV2Destination, batch: FeedMutationBatchV2,
                             completionHandler: @escaping (FeedV2RemoteResult<FeedMutationBatchResultV2>?, Error?) -> Void) {
        postCount += 1
        let row = FeedSnapshotV2(kind: "feed", id: instance, url: feedURL, version: 1,
                                 title: result == .applied ? "Local" : "Server",
                                 isActive: KotlinBoolean(bool: true), mode: "raw",
                                 maxArticles: KotlinInt(int: 5))
        let receipts = batch.mutations.map {
            FeedMutationResultV2(opId: $0.opId,
                                 status: result == .applied ? "applied" : "conflict",
                                 current: row, code: nil, message: nil)
        }
        completionHandler(FeedV2RemoteResultSuccess(value: FeedMutationBatchResultV2(
            serverInstanceId: instance, results: receipts)), nil)
    }
}
#endif
