import Foundation
import SwiftData
import Testing
import Domain
import GhostwriterClient
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
    private var key: String {
        ArticleDeliveryIdentityBridge.identify("https://example.test/article")!.articleKey
    }
    private let diagnostics = GenerationDiagnostics(feeds: [FeedIngestionResult(feedUrl: "https://feed.test/rss")])

    private func reopened(_ directory: URL) throws -> ModelContainer {
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        let configuration = ModelConfiguration(schema: schema,
                                               url: directory.appendingPathComponent("Epilogue.sqlite"))
        return try ModelContainer(for: schema, migrationPlan: EpilogueMigrationPlan.self,
                                  configurations: [configuration])
    }

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

    @Test("An interrupted run becomes retryable on reopen, once, without touching remote jobs")
    func testInterruptedRecoveryAndSecondRestart() throws {
        let (container, directory) = try model()
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let store = DeliveryStore(container: container)
        let run = try store.start(trigger: TriggerType.scheduled.rawValue,
                                  period: "MORNING", at: now)
        try store.markAttempts([DeliveryClaim(feedUrl: feed, articleKey: key,
                                               state: "retryable")], run: run)
        let context = ModelContext(container)
        let local = Digest(generatedAt: now, epubFilePath: "/tmp/legacy-pending.epub",
                           triggerType: .scheduled, period: "MORNING")
        let remote = Digest(generatedAt: now, epubFilePath: "/tmp/remote-pending.epub",
                            triggerType: .ghostwriter)
        let remoteRun = GenerationRun(attemptSequence: 2, startedAt: now,
                                      trigger: TriggerType.ghostwriter.rawValue,
                                      period: "MORNING")
        context.insert(local)
        context.insert(remote)
        context.insert(remoteRun)
        try context.save()

        let recovered = DeliveryStore(container: try reopened(directory))
        try recovered.reconcileInterruptedLocalRuns(now: now.addingTimeInterval(30))
        let after = ModelContext(try reopened(directory))
        let rows = try after.fetch(FetchDescriptor<GenerationRun>())
        let localRun = try #require(rows.first(where: { $0.runId == run.id }))
        #expect(localRun.outcome == "failed")
        #expect(localRun.finishedAt != nil)
        #expect(rows.first(where: { $0.runId == remoteRun.runId })?.outcome == "running")
        let recoveredDiagnostics = try JSONDecoder().decode(
            GenerationDiagnostics.self, from: Data(localRun.diagnosticsJSON.utf8))
        #expect(recoveredDiagnostics.runError == "interrupted")
        #expect(try #require(after.fetch(FetchDescriptor<ArticleDelivery>()).first).state == "retryable")
        let digests = try after.fetch(FetchDescriptor<Digest>())
        #expect(digests.first(where: { $0.id == local.id })?.errorMessage == "Interrupted local generation")
        #expect(digests.first(where: { $0.id == remote.id })?.errorMessage == nil)
        try DeliveryStore(container: try reopened(directory)).reconcileInterruptedLocalRuns(
            now: now.addingTimeInterval(60))
        let second = try ModelContext(try reopened(directory)).fetch(FetchDescriptor<GenerationRun>())
        #expect(second.first(where: { $0.runId == run.id })?.outcome == "failed")
        #expect(second.first(where: { $0.runId == run.id })?.finishedAt == now.addingTimeInterval(30))
    }

    @Test("A running row with a provable committed local artifact retains its claim")
    func testPostCommitRecovery() throws {
        let (container, directory) = try model()
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let path = try artifact(directory)
        let digest = Digest(generatedAt: now, epubFilePath: path, articleCount: 1,
                            triggerType: .scheduled, isComplete: true, period: "MORNING")
        let run = GenerationRun(attemptSequence: 1, startedAt: now,
                                trigger: TriggerType.scheduled.rawValue,
                                period: "MORNING", digestId: digest.id)
        let claim = ArticleDelivery(feedUrl: feed, articleKey: key, state: "delivered",
                                    firstDigestId: digest.id, committedAt: now)
        let association = article().toDigestArticle(contentType: .deepDive, orderIndex: 0)
        association.digest = digest
        let context = ModelContext(container)
        context.insert(digest)
        context.insert(association)
        context.insert(run)
        context.insert(claim)
        try context.save()
        let store = DeliveryStore(container: try reopened(directory))
        try store.reconcileInterruptedLocalRuns(now: now.addingTimeInterval(20))
        let after = ModelContext(try reopened(directory))
        #expect(try #require(after.fetch(FetchDescriptor<GenerationRun>()).first).outcome == "complete")
        #expect(try #require(after.fetch(FetchDescriptor<ArticleDelivery>()).first).firstDigestId == digest.id)
        #expect(try #require(after.fetch(FetchDescriptor<Digest>()).first).isComplete)
        #expect(FileManager.default.fileExists(atPath: path))
    }

    @Test("Scheduled admission allows one retry, not a third, and resets next day")
    func testScheduledAdmissionBudgetAndCoverage() throws {
        let (container, directory) = try model()
        let day = Date(timeIntervalSince1970: 1_800_000_000)
        let next = day.addingTimeInterval(86_400)
        let store = DeliveryStore(container: container)
        #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                            occurrenceEnd: next, legacyCovered: false))
        let first = try store.start(trigger: "SCHEDULED", period: "MORNING", at: day)
        _ = try store.finish(first, outcome: .failed, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [],
                             triggerType: .scheduled, period: "MORNING")
        #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                            occurrenceEnd: next, legacyCovered: false))
        let retry = try store.start(trigger: "SCHEDULED", period: "MORNING",
                                    at: day.addingTimeInterval(60))
        _ = try store.finish(retry, outcome: .failed, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [],
                             triggerType: .scheduled, period: "MORNING")
        let second = DeliveryStore(container: try reopened(directory))
        #expect(try !second.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                              occurrenceEnd: next, legacyCovered: false))
        #expect(try second.mayStartScheduled(period: "MORNING", occurrenceStart: next,
                                             occurrenceEnd: next.addingTimeInterval(86_400),
                                             legacyCovered: false))
        #expect(try !second.mayStartScheduled(period: "MORNING", occurrenceStart: next,
                                              occurrenceEnd: next.addingTimeInterval(86_400),
                                              legacyCovered: true))
    }

    @Test("Empty and deferred scheduled runs cover a window; manual runs do not spend its budget")
    func testSettledCoverageAndManualIndependence() throws {
        for outcome in [LocalGenerationOutcome.empty, .deferred, .partial, .complete] {
            let (container, _) = try model()
            let day = Date(timeIntervalSince1970: 1_800_000_000)
            let store = DeliveryStore(container: container)
            let manual = try store.start(trigger: "MANUAL", period: "manual", at: day)
            _ = try store.finish(manual, outcome: .empty, diagnostics: diagnostics,
                                 mode: .normal, artifactPath: nil, articles: [], claims: [],
                                 triggerType: .manual, period: "manual")
            #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                                occurrenceEnd: day.addingTimeInterval(86_400),
                                                legacyCovered: false))
            // The admission query reads persisted outcomes, regardless of
            // whether a downloadable digest exists for this fixture.
            let context = ModelContext(container)
            context.insert(GenerationRun(attemptSequence: 2, startedAt: day,
                                         trigger: "SCHEDULED", period: "MORNING",
                                         outcome: outcome.rawValue))
            try context.save()
            #expect(try !store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                                 occurrenceEnd: day.addingTimeInterval(86_400),
                                                 legacyCovered: false))
        }
    }

    @Test("Provable standalone legacy failures spend one retry and linked history is counted once")
    func testLegacyAttemptCounting() throws {
        let (container, _) = try model()
        let day = Date(timeIntervalSince1970: 1_800_000_000)
        let store = DeliveryStore(container: container)
        let context = ModelContext(container)
        let legacy = Digest(generatedAt: day, epubFilePath: "/tmp/old.epub",
                            triggerType: .scheduled, isComplete: false,
                            errorMessage: "Interrupted local generation", period: "MORNING")
        context.insert(legacy)
        context.insert(Digest(generatedAt: day, epubFilePath: "/tmp/ambiguous.epub",
                              triggerType: .scheduled, isComplete: false,
                              errorMessage: "Interrupted local generation", period: nil))
        try context.save()
        #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                            occurrenceEnd: day.addingTimeInterval(86_400),
                                            legacyCovered: false))
        let run = try store.start(trigger: "SCHEDULED", period: "MORNING", at: day)
        _ = try store.finish(run, outcome: .failed, diagnostics: diagnostics,
                             mode: .normal, artifactPath: nil, articles: [], claims: [],
                             triggerType: .scheduled, period: "MORNING")
        #expect(try !store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                             occurrenceEnd: day.addingTimeInterval(86_400),
                                             legacyCovered: false))
        // When a journal row explicitly references the same digest it is one
        // attempt, never two.
        let row = try #require(context.fetch(FetchDescriptor<GenerationRun>()).first)
        row.digestId = legacy.id
        try context.save()
        #expect(try store.mayStartScheduled(period: "MORNING", occurrenceStart: day,
                                            occurrenceEnd: day.addingTimeInterval(86_400),
                                            legacyCovered: false))
    }
}
