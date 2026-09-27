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
        let schema = Schema(versionedSchema: EpilogueSchemaV2.self)
        let configuration = ModelConfiguration(schema: schema,
                                                url: directory.appendingPathComponent("Epilogue.sqlite"))
        return try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                  configurations: [configuration])
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
