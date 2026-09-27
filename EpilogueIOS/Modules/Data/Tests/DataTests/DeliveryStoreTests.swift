import Foundation
import SwiftData
import Testing
import Domain
@testable import Data

@Suite("Durable local delivery store")
@MainActor
struct DeliveryStoreTests {
    private func model() throws -> (ModelContainer, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("delivery-store-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                               url: directory.appendingPathComponent("Epilogue.sqlite"))
        return (try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                   configurations: [configuration]), directory)
    }

    private let feed = "https://feed.test/rss"
    private let key = "article-key"
    private let diagnostics = GenerationDiagnostics(feeds: [FeedIngestionResult(feedUrl: "https://feed.test/rss")])

    private func article() -> ProcessedArticle {
        ProcessedArticle(title: "Article", content: "<p>Body</p>",
                         originalUrl: "https://example.test/article", feedUrl: feed,
                         feedName: "Feed", isSummary: false)
    }

    private func artifact(_ directory: URL) throws -> String {
        let url = directory.appendingPathComponent("\(UUID().uuidString).epub")
        try Data("EPUB".utf8).write(to: url)
        return url.path
    }

    @Test("Independent contexts reject a duplicate normal claim without a losing history row")
    func testIndependentClaimRollback() throws {
        let (container, directory) = try model()
        let first = DeliveryStore(container: container)
        let second = DeliveryStore(container: container)
        let run1 = try first.start(trigger: "MANUAL", period: "manual")
        let run2 = try second.start(trigger: "MANUAL", period: "manual")
        let claim = DeliveryClaim(feedUrl: feed, articleKey: key, state: "delivered",
                                  filterSignature: "signature-a")
        try first.markAttempts([claim], run: run1)
        try second.markAttempts([claim], run: run2)
        let winner = try first.finish(run1, outcome: .complete, diagnostics: diagnostics,
                                      mode: .normal, artifactPath: artifact(directory),
                                      articles: [article()], claims: [claim],
                                      triggerType: .manual, period: "manual")
        #expect(winner != nil)
        #expect(throws: DeliveryStoreError.invalidClaim) {
            try first.finish(run1, outcome: .failed, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [],
                             triggerType: .manual, period: "manual")
        }
        #expect(throws: DeliveryStoreError.alreadyDelivered) {
            try second.finish(run2, outcome: .complete, diagnostics: diagnostics,
                              mode: .normal, artifactPath: artifact(directory),
                              articles: [article()], claims: [claim],
                              triggerType: .manual, period: "manual")
        }
        _ = try second.finish(run2, outcome: .conflict, diagnostics: diagnostics,
                              mode: .normal, artifactPath: nil, articles: [], claims: [],
                              triggerType: .manual, period: "manual")
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 1)
        let ledgers = try reopened.fetch(FetchDescriptor<ArticleDelivery>())
        #expect(ledgers.count == 1)
        #expect(ledgers.first?.firstDigestId == winner?.id)
        #expect(try reopened.fetch(FetchDescriptor<GenerationRun>()).count == 2)
        #expect(try reopened.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == run1.id })?.outcome == "complete")
    }

    @Test("Injected finalization failure rolls back history, association and claim")
    func testFinalizationRollback() throws {
        let (container, directory) = try model()
        let store = DeliveryStore(container: container)
        let run = try store.start(trigger: "MANUAL", period: nil)
        let claim = DeliveryClaim(feedUrl: feed, articleKey: key, state: "delivered")
        try store.markAttempts([claim], run: run)
        store.failNextFinalSaveForTesting = true
        #expect(throws: DeliveryStoreError.injectedSaveFailure) {
            try store.finish(run, outcome: .complete, diagnostics: diagnostics,
                             mode: .normal, artifactPath: artifact(directory),
                             articles: [article()], claims: [claim],
                             triggerType: .manual, period: nil)
        }
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 0)
        #expect(try reopened.fetchCount(FetchDescriptor<DigestArticle>()) == 0)
        let ledger = try #require(reopened.fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(ledger.state == "retryable")
        #expect(ledger.firstDigestId == nil)
        #expect(try #require(reopened.fetch(FetchDescriptor<GenerationRun>()).first).outcome == "running")
    }

    @Test("A thrown transaction before its single commit rolls back history and claims")
    func testPreCommitTransactionRollback() throws {
        let (container, directory) = try model()
        let store = DeliveryStore(container: container)
        let run = try store.start(trigger: "MANUAL", period: nil)
        let claim = DeliveryClaim(feedUrl: feed, articleKey: key, state: "delivered")
        try store.markAttempts([claim], run: run)
        store.failBeforeTransactionCommitForTesting = true
        #expect(throws: DeliveryStoreError.injectedSaveFailure) {
            try store.finish(run, outcome: .complete, diagnostics: diagnostics,
                             mode: .normal, artifactPath: artifact(directory),
                             articles: [article()], claims: [claim],
                             triggerType: .manual, period: nil)
        }
        let reopened = ModelContext(container)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 0)
        #expect(try reopened.fetchCount(FetchDescriptor<DigestArticle>()) == 0)
        let ledger = try #require(reopened.fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(ledger.state == "retryable")
        #expect(ledger.firstDigestId == nil)
        #expect(try #require(reopened.fetch(FetchDescriptor<GenerationRun>()).first).outcome == "running")
    }

    @Test("Failed run cannot commit a terminal exclusion")
    func testFailedRunDoesNotExclude() throws {
        let (container, _) = try model()
        let store = DeliveryStore(container: container)
        let run = try store.start(trigger: "MANUAL", period: nil)
        let excluded = DeliveryClaim(feedUrl: feed, articleKey: key, state: "excluded",
                                     reason: "content_too_short", filterSignature: "a")
        try store.markAttempts([excluded], run: run)
        #expect(throws: DeliveryStoreError.invalidClaim) {
            try store.finish(run, outcome: .failed, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [excluded],
                             triggerType: .manual, period: nil)
        }
        let ledger = try #require(ModelContext(container).fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(ledger.state == "retryable")
    }

    @Test("Excluded signature and regeneration preserve first delivery after history deletion")
    func testExclusionAndRegeneration() async throws {
        let (container, directory) = try model()
        let store = DeliveryStore(container: container)
        let excluded = DeliveryClaim(feedUrl: feed, articleKey: key, state: "excluded",
                                     reason: "content_too_short", filterSignature: "signature-a")
        let filteredRun = try store.start(trigger: "MANUAL", period: nil)
        try store.markAttempts([excluded], run: filteredRun)
        _ = try store.finish(filteredRun, outcome: .empty, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [excluded],
                             triggerType: .manual, period: nil)
        let sameSignature = try store.start(trigger: "MANUAL", period: nil)
        #expect(throws: DeliveryStoreError.invalidClaim) {
            try store.finish(sameSignature, outcome: .complete, diagnostics: diagnostics,
                             mode: .normal, artifactPath: artifact(directory),
                             articles: [article()], claims: [DeliveryClaim(
                                feedUrl: feed, articleKey: key, state: "delivered",
                                filterSignature: "signature-a")],
                             triggerType: .manual, period: nil)
        }
        let changed = DeliveryClaim(feedUrl: feed, articleKey: key, state: "delivered",
                                    filterSignature: "signature-b")
        let firstDigest = try #require(try store.finish(sameSignature, outcome: .complete,
                                                    diagnostics: diagnostics, mode: .normal,
                                                    artifactPath: artifact(directory),
                                                    articles: [article()], claims: [changed],
                                                    triggerType: .manual, period: nil))
        let repository = DigestRepository(modelContext: ModelContext(container))
        try await repository.deleteDigest(id: firstDigest.id)
        let regenerate = try store.start(trigger: "MANUAL", period: nil)
        try store.markAttempts([changed], run: regenerate)
        _ = try store.finish(regenerate, outcome: .complete, diagnostics: diagnostics,
                             mode: .regenerate, artifactPath: artifact(directory),
                             articles: [article()], claims: [changed],
                             triggerType: .manual, period: nil)
        let reopened = ModelContext(container)
        let ledger = try #require(reopened.fetch(FetchDescriptor<ArticleDelivery>()).first)
        #expect(ledger.state == "delivered")
        #expect(ledger.firstDigestId == firstDigest.id)
        #expect(try reopened.fetchCount(FetchDescriptor<Digest>()) == 1)
    }
}
