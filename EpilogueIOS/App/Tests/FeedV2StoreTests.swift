import XCTest
import SwiftData
import Domain
import Data
@testable import Epilogue

@MainActor
final class FeedV2StoreTests: XCTestCase {
    private let feedURL = "https://example.test/feed.xml"

    private func model() throws -> ModelContainer {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("feed-v2-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        // SwiftData may retain the SQLite handle past XCTest teardown. Removing
        // the live file triggered SQLite's vnode-unlinked integrity warning.
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                                url: directory.appendingPathComponent("Epilogue.sqlite"))
        return try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                  configurations: [configuration])
    }

    private func resolutionFixture(kind: String = "upsert", status: String = "conflict",
                                   serverSnapshot: Bool = true,
                                   locallyDeleted: Bool = false) throws ->
        (ModelContainer, IOSFeedV2StoreEngine, String) {
        let container = try model()
        let context = ModelContext(container)
        let scope = "https://server.test\nconfiguration"
        context.insert(FeedSyncState(destinationURL: "https://server.test",
                                     configurationId: "configuration",
                                     firstReconciliationComplete: true))
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
