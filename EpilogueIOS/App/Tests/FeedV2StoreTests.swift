import XCTest
import SwiftData
import Domain
import Data
@testable import Epilogue

@MainActor
final class FeedV2StoreTests: XCTestCase {
    private let feedURL = "https://example.test/feed.xml"

    private func model(at storeURL: URL? = nil) throws -> ModelContainer {
        let url = storeURL ?? FileManager.default.temporaryDirectory
            .appendingPathComponent("feed-v2-\(UUID().uuidString)", isDirectory: true)
            .appendingPathComponent("Epilogue.sqlite")
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        // SwiftData may retain the SQLite handle past XCTest teardown. Removing
        // the live file triggered SQLite's vnode-unlinked integrity warning.
        let schema = Schema(versionedSchema: EpilogueSchemaV2.self)
        let configuration = ModelConfiguration(schema: schema, url: url)
        return try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                  configurations: [configuration])
    }

    private func resolutionFixture(kind: String = "upsert", status: String = "conflict",
                                   serverSnapshot: Bool = true,
                                   locallyDeleted: Bool = false,
                                   storeURL: URL? = nil) throws ->
        (ModelContainer, IOSFeedV2StoreEngine, String) {
        let container = try model(at: storeURL)
        let context = ModelContext(container)
        let scope = "https://server.test\nconfiguration"
        context.insert(FeedSyncState(destinationURL: "https://server.test",
                                     configurationId: "configuration",
                                     firstReconciliationComplete: true,
                                     nextSequence: 2))
        context.insert(Domain.Feed(url: feedURL, name: "Server title", mode: .fidelity,
                                   maxArticles: 2, isEnabled: false,
                                   serverId: serverSnapshot ? "server-id" : nil,
                                   serverVersion: serverSnapshot ? 8 : nil,
                                   isLocallyDeleted: locallyDeleted))
        let proposal = FeedMutation(url: feedURL, scopeKey: scope, kind: kind,
                                    baseVersion: serverSnapshot ? 7 : nil,
                                    title: kind == "delete" ? nil : "My title",
                                    isActive: true, mode: "summarize", maxArticles: 5,
                                    sequence: 1, localRevision: 1, status: status, sent: true)
        if serverSnapshot {
            proposal.serverKind = "feed"
            proposal.serverId = "server-id"
            proposal.serverVersion = 8
            proposal.serverTitle = "Server title"
            proposal.serverIsActive = false
            proposal.serverMode = "raw"
            proposal.serverMaxArticles = 2
        }
        context.insert(proposal)
        try context.save()
        return (container, IOSFeedV2StoreEngine(container: container), proposal.opId)
    }

    private func resolvedRow(_ container: ModelContainer) throws -> Domain.Feed {
        try XCTUnwrap(ModelContext(container).fetch(FetchDescriptor<Domain.Feed>()).first)
    }

    private func rejectedCreateFixture(storeURL: URL? = nil) throws ->
        (ModelContainer, IOSFeedV2StoreEngine, String) {
        let container = try model(at: storeURL)
        let context = ModelContext(container)
        context.insert(FeedSyncState(destinationURL: "https://server.test",
                                     configurationId: "configuration",
                                     firstReconciliationComplete: true,
                                     nextSequence: 1))
        try context.save()
        let engine = IOSFeedV2StoreEngine(container: container)
        try engine.edit(url: feedURL, title: "Rejected title", mode: .fidelity,
                        isEnabled: true, maxArticles: 2)
        let head = try XCTUnwrap(ModelContext(container).fetch(FetchDescriptor<FeedMutation>()).first)
        let update = ModelContext(container)
        let persisted = try XCTUnwrap(update.fetch(FetchDescriptor<FeedMutation>()).first)
        persisted.status = "rejected"
        persisted.sent = true
        try update.save()
        return (container, engine, head.opId)
    }

    private func orderedMutations(_ container: ModelContainer) throws -> [FeedMutation] {
        try ModelContext(container).fetch(FetchDescriptor<FeedMutation>())
            .sorted { $0.sequence < $1.sequence }
    }

    func testApplyMineRestoresVisibleProposalWithReplacementAndReopen() throws {
        let (container, engine, opId) = try resolutionFixture()
        try engine.resolve(opId: opId, action: .applyMine)
        let visible = try resolvedRow(container)
        XCTAssertEqual(visible.name, "My title")
        XCTAssertEqual(visible.mode, .briefing)
        XCTAssertTrue(visible.isEnabled)
        XCTAssertEqual(visible.maxArticles, 5)
        XCTAssertFalse(visible.isLocallyDeleted ?? true)
        XCTAssertEqual(visible.mutationRevision, 2)
        let replacement = try XCTUnwrap(ModelContext(container).fetch(FetchDescriptor<FeedMutation>()).first)
        XCTAssertNotEqual(replacement.opId, opId)
        XCTAssertEqual(replacement.sequence, 1)
        XCTAssertEqual(replacement.baseVersion, 8)
        XCTAssertEqual(replacement.title, visible.name)
    }

    func testAddToServerUnhidesAbsentFeedWithProposal() throws {
        let (container, engine, opId) = try resolutionFixture(status: "needs_resolution",
                                                                serverSnapshot: false,
                                                                locallyDeleted: true)
        try engine.resolve(opId: opId, action: .addToServer)
        let visible = try resolvedRow(container)
        XCTAssertEqual(visible.name, "My title")
        XCTAssertFalse(visible.isLocallyDeleted ?? true)
        XCTAssertEqual(visible.mode, .briefing)
        XCTAssertEqual(visible.maxArticles, 5)
        let replacement = try XCTUnwrap(ModelContext(container).fetch(FetchDescriptor<FeedMutation>()).first)
        XCTAssertNil(replacement.baseVersion)
        XCTAssertEqual(replacement.title, "My title")
    }

    func testCorrectRejectedEditUpdatesVisibleTitleAndRollsBackTogether() throws {
        let (container, engine, opId) = try resolutionFixture(status: "rejected")
        engine.failNextSaveForTesting = true
        XCTAssertThrowsError(try engine.resolve(opId: opId, action: .correct,
                                                correctedTitle: "Corrected title"))
        XCTAssertEqual(try resolvedRow(container).name, "Server title")
        XCTAssertEqual(try ModelContext(container).fetch(FetchDescriptor<FeedMutation>()).first?.opId,
                       opId)
        try engine.resolve(opId: opId, action: .correct, correctedTitle: "Corrected title")
        XCTAssertEqual(try resolvedRow(container).name, "Corrected title")
        XCTAssertFalse(try resolvedRow(container).isLocallyDeleted ?? true)
        let replacement = try XCTUnwrap(ModelContext(container).fetch(FetchDescriptor<FeedMutation>()).first)
        XCTAssertEqual(replacement.title, "Corrected title")
        XCTAssertEqual(replacement.baseVersion, 8)
    }

    func testRejectedDeleteCannotEnterTitleCorrection() throws {
        let (_, engine, opId) = try resolutionFixture(kind: "delete", status: "rejected")
        XCTAssertThrowsError(try engine.resolve(opId: opId, action: .correct,
                                                correctedTitle: "Ignored title"))
    }

    func testCorrectRejectedHeadPreservesOverlappingAndDisjointSuccessorEdits() throws {
        let (container, engine, opId) = try resolutionFixture(status: "rejected")
        try engine.edit(url: feedURL, title: "Later title", mode: .fidelity,
                        isEnabled: false, maxArticles: 9)
        try engine.resolve(opId: opId, action: .correct, correctedTitle: "Corrected head")
        let visible = try resolvedRow(container)
        XCTAssertEqual(visible.name, "Later title")
        XCTAssertEqual(visible.mode, .briefing)
        XCTAssertTrue(visible.isEnabled)
        XCTAssertEqual(visible.maxArticles, 9)
        XCTAssertFalse(visible.isLocallyDeleted ?? true)
        XCTAssertEqual(visible.mutationRevision, 2)
        let queued = try ModelContext(container).fetch(FetchDescriptor<FeedMutation>())
            .sorted { $0.sequence < $1.sequence }
        XCTAssertEqual(queued.count, 2)
        XCTAssertEqual(queued[0].title, "Corrected head")
        XCTAssertEqual(queued[1].title, "Later title")
        XCTAssertEqual(try resolvedRow(container).name, "Later title")
    }

    func testResolvingOlderUpsertKeepsLaterDeleteHiddenAcrossReopen() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("feed-v2-reopen-\(UUID().uuidString)", isDirectory: true)
            .appendingPathComponent("Epilogue.sqlite")
        do {
            let (container, engine, opId) = try resolutionFixture(status: "rejected",
                                                                    storeURL: url)
            try engine.delete(url: feedURL)
            try engine.resolve(opId: opId, action: .correct, correctedTitle: "Corrected head")
            XCTAssertTrue(try resolvedRow(container).isLocallyDeleted ?? false)
        }
        let reopened = try model(at: url)
        let queued = try ModelContext(reopened).fetch(FetchDescriptor<FeedMutation>())
            .sorted { $0.sequence < $1.sequence }
        XCTAssertEqual(queued.map(\.kind), ["upsert", "delete"])
        XCTAssertTrue(try resolvedRow(reopened).isLocallyDeleted ?? false)
    }

    func testResolvingDeleteReplaysLaterReaddAndDeleteAcrossReopen() throws {
        for (changedTitle, trailingDelete) in [(false, false), (true, false), (true, true)] {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("feed-v2-delete-successor-\(UUID().uuidString)", isDirectory: true)
                .appendingPathComponent("Epilogue.sqlite")
            do {
                let (container, engine, opId) = try resolutionFixture(
                    kind: "delete", locallyDeleted: true, storeURL: url)
                let expectedTitle = changedTitle ? "Re-added title" : "Server title"
                try engine.edit(url: feedURL, title: expectedTitle, mode: .fidelity,
                                isEnabled: false, maxArticles: 2)
                let before = try orderedMutations(container)
                XCTAssertEqual(before.map(\.kind), ["delete", "upsert"])
                XCTAssertEqual(before[1].title, changedTitle ? expectedTitle : nil)
                let successorId = before[1].opId
                if trailingDelete { try engine.delete(url: feedURL) }
                let originalIds = try orderedMutations(container).map(\.opId)

                engine.failNextSaveForTesting = true
                XCTAssertThrowsError(try engine.resolve(opId: opId, action: .applyMine))
                XCTAssertEqual(try resolvedRow(container).isLocallyDeleted ?? false, trailingDelete)
                XCTAssertEqual(try orderedMutations(container).map(\.opId), originalIds)

                try engine.resolve(opId: opId, action: .applyMine)
                let visible = try resolvedRow(container)
                XCTAssertEqual(visible.isLocallyDeleted ?? false, trailingDelete)
                XCTAssertEqual(visible.name, expectedTitle)
                let queued = try orderedMutations(container)
                XCTAssertEqual(queued.map(\.kind), trailingDelete
                               ? ["delete", "upsert", "delete"] : ["delete", "upsert"])
                XCTAssertNotEqual(queued[0].opId, opId)
                XCTAssertEqual(queued[0].baseVersion, 8)
                XCTAssertEqual(queued[1].opId, successorId)
                XCTAssertEqual(queued[1].title, changedTitle ? expectedTitle : nil)
            }
            let reopened = try model(at: url)
            XCTAssertEqual(try resolvedRow(reopened).isLocallyDeleted ?? false, trailingDelete)
            XCTAssertEqual(try resolvedRow(reopened).name,
                           changedTitle ? "Re-added title" : "Server title")
            XCTAssertEqual(try orderedMutations(reopened).map(\.kind), trailingDelete
                           ? ["delete", "upsert", "delete"] : ["delete", "upsert"])
        }
    }

    func testRejectedCreateCorrectionKeepsCapOnlySuccessorSparseAcrossReopen() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("feed-v2-create-successor-\(UUID().uuidString)")
            .appendingPathComponent("Epilogue.sqlite")
        do {
            let (container, engine, opId) = try rejectedCreateFixture(storeURL: url)
            try engine.edit(url: feedURL, title: "Rejected title", mode: .fidelity,
                            isEnabled: true, maxArticles: 9)
            let before = try orderedMutations(container)
            XCTAssertEqual(before.count, 2)
            XCTAssertEqual(before[0].title, "Rejected title")
            XCTAssertNil(before[1].title)
            XCTAssertNil(before[1].isActive)
            XCTAssertNil(before[1].mode)
            XCTAssertEqual(before[1].maxArticles, 9)
            try engine.resolve(opId: opId, action: .correct, correctedTitle: "Corrected title")
            XCTAssertEqual(try resolvedRow(container).name, "Corrected title")
            XCTAssertEqual(try resolvedRow(container).maxArticles, 9)
            let after = try orderedMutations(container)
            XCTAssertEqual(after[0].title, "Corrected title")
            XCTAssertNil(after[1].title)
        }
        let reopened = try model(at: url)
        XCTAssertEqual(try resolvedRow(reopened).name, "Corrected title")
        XCTAssertEqual(try resolvedRow(reopened).maxArticles, 9)
        XCTAssertNil(try orderedMutations(reopened)[1].title)
    }

    func testRejectedCreateCorrectionPreservesIntentionalNewerTitleAndDelete() throws {
        let (container, engine, opId) = try rejectedCreateFixture()
        try engine.edit(url: feedURL, title: "Intentional later title", mode: .fidelity,
                        isEnabled: true, maxArticles: 2)
        try engine.resolve(opId: opId, action: .correct, correctedTitle: "Corrected head")
        XCTAssertEqual(try resolvedRow(container).name, "Intentional later title")
        XCTAssertEqual(try orderedMutations(container)[1].title, "Intentional later title")
        try engine.delete(url: feedURL)
        XCTAssertTrue(try resolvedRow(container).isLocallyDeleted ?? false)
        XCTAssertEqual(try orderedMutations(container).map(\.kind), ["upsert", "upsert", "delete"])
    }

    func testRejectedCreateDiscardMakesSparseSuccessorExplicitCompleteCreate() throws {
        let (container, engine, opId) = try rejectedCreateFixture()
        try engine.edit(url: feedURL, title: "Rejected title", mode: .fidelity,
                        isEnabled: true, maxArticles: 9)
        try engine.resolve(opId: opId, action: .discard)
        let successor = try XCTUnwrap(orderedMutations(container).first)
        XCTAssertEqual(successor.status, "needs_resolution")
        XCTAssertEqual(successor.title, "Rejected title")
        XCTAssertEqual(successor.isActive, true)
        XCTAssertEqual(successor.mode, "raw")
        XCTAssertEqual(successor.maxArticles, 9)
        try engine.resolve(opId: successor.opId, action: .addToServer)
        let replacement = try XCTUnwrap(orderedMutations(container).first)
        XCTAssertNil(replacement.baseVersion)
        XCTAssertEqual(replacement.title, "Rejected title")
        XCTAssertEqual(replacement.maxArticles, 9)
    }

    func testThreeCreateQueueRetainsCompleteHeadAfterDiscardOrKeepRemovedAndReopen() throws {
        for firstAction in [IOSFeedV2StoreEngine.Resolution.discard, .keepRemoved] {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("feed-v2-three-create-\(UUID().uuidString)")
                .appendingPathComponent("Epilogue.sqlite")
            do {
                let (container, engine, headId) = try rejectedCreateFixture(storeURL: url)
                try engine.edit(url: feedURL, title: "Rejected title", mode: .fidelity,
                                isEnabled: true, maxArticles: 9)
                try engine.edit(url: feedURL, title: "Newest title", mode: .fidelity,
                                isEnabled: true, maxArticles: 9)
                let before = try orderedMutations(container)
                XCTAssertEqual(before.count, 3)
                XCTAssertNil(before[1].title)
                XCTAssertEqual(before[1].maxArticles, 9)
                XCTAssertEqual(before[2].title, "Newest title")
                XCTAssertNil(before[2].maxArticles)
                try engine.resolve(opId: headId, action: firstAction)
            }
            let reopened = try model(at: url)
            let engine = IOSFeedV2StoreEngine(container: reopened)
            let middle = try XCTUnwrap(orderedMutations(reopened).first)
            XCTAssertEqual(middle.title, "Rejected title")
            XCTAssertEqual(middle.maxArticles, 9)
            try engine.resolve(opId: middle.opId, action: .keepRemoved)
            let final = try XCTUnwrap(orderedMutations(reopened).first)
            XCTAssertEqual(final.title, "Newest title")
            XCTAssertEqual(final.isActive, true)
            XCTAssertEqual(final.mode, "raw")
            XCTAssertEqual(final.maxArticles, 9)
            try engine.resolve(opId: final.opId, action: .addToServer)
            let queued = try XCTUnwrap(orderedMutations(reopened).first)
            XCTAssertEqual(queued.title, "Newest title")
            XCTAssertEqual(queued.maxArticles, 9)
            XCTAssertNil(queued.baseVersion)
        }
    }

    func testOldScopePromotionRetainsCompleteCreateAfterTransferOrDiscard() throws {
        for firstAction in [IOSFeedV2StoreEngine.PreviousProposalAction.transfer, .discard] {
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("feed-v2-old-scope-create-\(UUID().uuidString)")
                .appendingPathComponent("Epilogue.sqlite")
            do {
                let (container, engine, headId) = try rejectedCreateFixture(storeURL: url)
                try engine.edit(url: feedURL, title: "Rejected title", mode: .fidelity,
                                isEnabled: true, maxArticles: 9)
                let sparse = try XCTUnwrap(orderedMutations(container).last)
                XCTAssertNil(sparse.title)
                XCTAssertEqual(sparse.maxArticles, 9)
                _ = try engine.destination(for: "https://replacement.test")
                try engine.startNewBinding()
                let context = ModelContext(container)
                let state = try XCTUnwrap(context.fetch(FetchDescriptor<FeedSyncState>()).first)
                state.firstReconciliationComplete = true
                try context.save()
                try engine.resolvePrevious(opId: headId, action: firstAction)
            }
            let reopened = try model(at: url)
            let engine = IOSFeedV2StoreEngine(container: reopened)
            let state = try XCTUnwrap(ModelContext(reopened)
                .fetch(FetchDescriptor<FeedSyncState>()).first)
            let currentScope = try XCTUnwrap(state.destinationURL) + "\n" +
                (try XCTUnwrap(state.configurationId))
            let successor = try XCTUnwrap(orderedMutations(reopened)
                .first(where: { $0.scopeKey != currentScope }))
            XCTAssertEqual(successor.title, "Rejected title")
            XCTAssertEqual(successor.isActive, true)
            XCTAssertEqual(successor.mode, "raw")
            XCTAssertEqual(successor.maxArticles, 9)
            try engine.resolvePrevious(opId: successor.opId, action: .transfer)
            let transferred = try XCTUnwrap(orderedMutations(reopened)
                .filter { $0.scopeKey == currentScope }.last)
            XCTAssertNil(transferred.baseVersion)
            XCTAssertEqual(transferred.title, "Rejected title")
            XCTAssertEqual(transferred.maxArticles, 9)
        }
    }

    func testClaimedCreatePayloadSurvivesTimeoutAndReopenWithSparseSuccessor() throws {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("feed-v2-claimed-create-\(UUID().uuidString)")
            .appendingPathComponent("Epilogue.sqlite")
        var firstOpId = ""
        var firstRevision: Int64 = -1
        do {
            let container = try model(at: url)
            let context = ModelContext(container)
            context.insert(FeedSyncState(destinationURL: "https://server.test",
                                         configurationId: "configuration",
                                         firstReconciliationComplete: true,
                                         nextSequence: 1))
            try context.save()
            let engine = IOSFeedV2StoreEngine(container: container)
            try engine.edit(url: feedURL, title: "Original create", mode: .fidelity,
                            isEnabled: true, maxArticles: 2)
            let claimed = try XCTUnwrap(engine.claimOneForTesting())
            firstOpId = claimed.opId
            firstRevision = claimed.sentRevision
            XCTAssertEqual(claimed.title, "Original create")
            XCTAssertEqual(claimed.isActive, true)
            XCTAssertEqual(claimed.mode, "raw")
            XCTAssertEqual(claimed.maxArticles, 2)
            try engine.edit(url: feedURL, title: "Original create", mode: .fidelity,
                            isEnabled: true, maxArticles: 9)
            // The claim has no acknowledgement, as after a request timeout.
            let rows = try orderedMutations(container)
            XCTAssertEqual(rows[0].opId, firstOpId)
            XCTAssertTrue(rows[0].sent)
            XCTAssertNil(rows[1].title)
        }
        let reopened = try model(at: url)
        let engine = IOSFeedV2StoreEngine(container: reopened)
        let retried = try XCTUnwrap(engine.claimOneForTesting())
        XCTAssertEqual(retried.opId, firstOpId)
        XCTAssertEqual(retried.sentRevision, firstRevision)
        XCTAssertEqual(retried.title, "Original create")
        XCTAssertEqual(retried.isActive, true)
        XCTAssertEqual(retried.mode, "raw")
        XCTAssertEqual(retried.maxArticles, 2)
        XCTAssertNil(try orderedMutations(reopened)[1].title)
    }

    func testOnlyCompleteFeedOutcomePersistsSuccessfulTimestamp() async throws {
        let defaults = UserDefaults(suiteName: "feed-outcome-\(UUID().uuidString)")!
        let settings = SettingsRepository(userDefaults: defaults)
        let prior = Date(timeIntervalSince1970: 1_700_000_000)
        try await settings.setLastFeedSyncTime(prior)
        let service = FeedSyncService(settingsRepository: settings, modelContainer: try model())
        do {
            try await service.apply(.partial(pending: 1, conflicts: 0,
                                             rejected: 0, phase: "pull"))
            XCTFail("Partial feed sync must not count as success")
        } catch is FeedSyncV2Error {}
        do {
            try await service.apply(.failed(phase: "pull", message: "offline"))
            XCTFail("Failed feed sync must not count as success")
        } catch is FeedSyncV2Error {}
        try await service.apply(.notConfigured)
        let unchanged = try await settings.getLastFeedSyncTime()
        XCTAssertEqual(unchanged, prior)
        let cancelled = Task { try await service.apply(.complete(applied: 1, pulled: 1)) }
        cancelled.cancel()
        do {
            try await cancelled.value
            XCTFail("Cancelled feed sync must not persist success")
        } catch is CancellationError {}
        let afterCancellation = try await settings.getLastFeedSyncTime()
        XCTAssertEqual(afterCancellation, prior)
        try await service.apply(.complete(applied: 1, pulled: 2))
        let reopened = SettingsRepository(userDefaults: defaults)
        let successful = try await reopened.getLastFeedSyncTime()
        XCTAssertGreaterThan(try XCTUnwrap(successful), prior)
    }

    func testEditAndSaveFailureRollback() throws {
        let container = try model()
        let engine = IOSFeedV2StoreEngine(container: container)
        engine.failNextSaveForTesting = true
        XCTAssertThrowsError(try engine.edit(url: feedURL, title: "Local", mode: .fidelity,
                                             isEnabled: true, maxArticles: 2))
        let context = ModelContext(container)
        XCTAssertEqual(try context.fetchCount(FetchDescriptor<Domain.Feed>()), 0)
        XCTAssertEqual(try context.fetchCount(FetchDescriptor<FeedMutation>()), 0)
        try engine.edit(url: feedURL, title: "Local", mode: .fidelity,
                        isEnabled: true, maxArticles: 2)
        XCTAssertEqual(try ModelContext(container).fetchCount(FetchDescriptor<FeedMutation>()), 1)
    }

    func testOfflineDeleteHiddenFromRepository() async throws {
        try await FeedV2TestHarness(model()).offlineDeleteAndReopenAssertion()
    }

    func testSentReplayAndSuccessor() throws {
        try FeedV2TestHarness(model()).replayAndSuccessorAssertion()
    }

    func testNewerServerWinsWithProposalRetained() throws {
        try FeedV2TestHarness(model()).newerServerWinsWithProposalAssertion()
    }

    func testNewerPullRefreshesConflictBeforeKeepServer() throws {
        try FeedV2TestHarness(model()).newerPullRefreshesConflictAssertion()
    }

    func testLegacyHeadThenPrebindEditCannotNullBaseCreate() throws {
        try FeedV2TestHarness(model()).legacyHeadThenPrebindEditAssertion()
    }

    func testPrebindingDeleteStaysHidden() async throws {
        try await FeedV2TestHarness(model()).prebindingDeleteStaysHiddenAssertion()
    }

    func testRejectedCreateDiscardRemovesLocalFeed() throws {
        try FeedV2TestHarness(model()).rejectedCreateDiscardAssertion()
    }

    func testRejectedEditDiscardRestoresServer() throws {
        try FeedV2TestHarness(model()).rejectedEditDiscardAssertion()
    }

    func testRejectedDeleteDiscardRestoresServerAndReopens() async throws {
        try await FeedV2TestHarness(model()).rejectedDeleteDiscardAssertion()
    }

    func testRejectedDeleteDiscardUsesNewerPull() throws {
        try FeedV2TestHarness(model()).rejectedDeleteDiscardKeepsNewerSnapshotAssertion()
    }

    func testRejectedDeleteSuccessorDiscardRestoresAcknowledgedServer() throws {
        try FeedV2TestHarness(model()).rejectedDeleteSuccessorDiscardAssertion()
    }

    func testKeepServerCarriesSnapshotToSuccessor() throws {
        try FeedV2TestHarness(model()).keepServerSuccessorSnapshotAssertion()
    }

    func testCorrectedRejectedEditKeepsBase() throws {
        try FeedV2TestHarness(model()).correctedRejectedEditKeepsBaseAssertion()
    }

    func testOldScopeCannotResolve() throws {
        try FeedV2TestHarness(model()).resolutionScopeAssertion()
    }

    func testResolutionIgnoresOtherScopeSuccessors() throws {
        try FeedV2TestHarness(model()).resolutionIgnoresOtherScopeSuccessorsAssertion()
    }

    func testInvalidInputDoesNotPersist() throws {
        try FeedV2TestHarness(model()).invalidInputRollsBackAssertion()
    }

    func testCursorSaveFailure() throws {
        try FeedV2TestHarness(model()).cursorFailureAssertion()
    }

    func testSameURLReplacementGetsFreshScope() throws {
        try FeedV2TestHarness(model()).bindingScopeAssertion()
    }

    func testConflictReplacementKeepsHeadSlot() throws {
        try FeedV2TestHarness(model()).replacementSlotAssertion()
    }

    func testExportedUseCaseAppliedThroughRealStorePort() async throws {
        try await FeedV2TestHarness(model()).exportedUseCaseAssertion(false)
    }

    func testExportedUseCaseConflictThroughRealStorePort() async throws {
        try await FeedV2TestHarness(model()).exportedUseCaseAssertion(true)
    }

    func testSwiftCancellationDoesNotReportComplete() async throws {
        try await FeedV2TestHarness(model()).cancellationAssertion()
    }

    func testHiddenPresentationKeepsAttentionButOmitsSettledTombstones() throws {
        let visible = Domain.Feed(url: "https://example.test/visible", name: "Visible", mode: .fidelity)
        let pending = Domain.Feed(url: "https://example.test/pending", name: "Pending", mode: .fidelity,
                                  isLocallyDeleted: true)
        let settled = Domain.Feed(url: "https://example.test/settled", name: "Settled", mode: .fidelity,
                                  isLocallyDeleted: true)
        let issue = FeedMutation(url: pending.url, scopeKey: "scope", kind: "delete",
                                 sequence: 1, localRevision: 1, status: "needs_resolution")
        let sections = FeedListView.partition([visible, pending, settled], mutations: [issue])
        XCTAssertEqual(sections.visible.map(\.url), [visible.url])
        XCTAssertEqual(sections.attention.map(\.url), [pending.url])
    }
}
