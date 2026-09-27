import Foundation
import SwiftData
import Testing
import Domain
@testable import Data

@Suite("Interrupted local artifact recovery")
@MainActor
struct DeliveryRecoveryTests {
    private enum BrokenArtifact: CaseIterable {
        case missingEPUB, missingAssociation, missingClaim
    }

    private func container(at directory: URL) throws -> ModelContainer {
        let schema = Schema(versionedSchema: EpilogueSchemaV3.self)
        return try ModelContainer(
            for: schema, migrationPlan: EpilogueMigrationPlan.self,
            configurations: [ModelConfiguration(
                schema: schema, url: directory.appendingPathComponent("Epilogue.sqlite"))])
    }

    private func fixture(_ broken: BrokenArtifact?) throws ->
        (directory: URL, digestId: UUID, runId: UUID, path: String, start: Date) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("delivery-recovery-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let path = directory.appendingPathComponent("edition.epub").path
        if broken != .missingEPUB { try Data("EPUB".utf8).write(to: URL(fileURLWithPath: path)) }
        let start = Date(timeIntervalSince1970: 1_800_000_000)
        let digest = Digest(generatedAt: start, epubFilePath: path, articleCount: 1,
                            triggerType: .scheduled, isComplete: true, period: "MORNING")
        let run = GenerationRun(attemptSequence: 1, startedAt: start,
                                trigger: TriggerType.scheduled.rawValue,
                                period: "MORNING", digestId: digest.id)
        let context = ModelContext(try container(at: directory))
        context.insert(digest)
        context.insert(run)
        if broken != .missingAssociation {
            context.insert(DigestArticle(
                digest: digest, title: "Article", content: "Body",
                originalUrl: "https://example.test/article",
                feedUrl: "https://feed.test/rss", feedName: "Feed",
                contentType: .deepDive))
        }
        if broken != .missingClaim {
            context.insert(ArticleDelivery(
                feedUrl: "https://feed.test/rss", articleKey: "article-key",
                state: "delivered", firstDigestId: digest.id, committedAt: start))
        }
        try context.save()
        return (directory, digest.id, run.runId, path, start)
    }

    @Test("Each unusable completed artifact releases coverage but spends only its original attempt")
    func brokenCompletedArtifactsRemainRetryable() async throws {
        for broken in BrokenArtifact.allCases {
            let value = try fixture(broken)
            let store = DeliveryStore(container: try container(at: value.directory))
            let interruptedAt = value.start.addingTimeInterval(30)
            try store.reconcileInterruptedLocalRuns(now: interruptedAt)

            let reopened = try container(at: value.directory)
            let context = ModelContext(reopened)
            let digest = try #require(context.fetch(FetchDescriptor<Digest>())
                .first(where: { $0.id == value.digestId }))
            let run = try #require(context.fetch(FetchDescriptor<GenerationRun>())
                .first(where: { $0.runId == value.runId }))
            #expect(run.outcome == "failed")
            #expect(run.finishedAt == interruptedAt)
            #expect(!digest.isComplete)
            #expect(digest.errorMessage == "Interrupted local generation")
            #expect(FileManager.default.fileExists(atPath: value.path) == (broken != .missingEPUB))
            #expect(try context.fetchCount(FetchDescriptor<DigestArticle>()) ==
                    (broken == .missingAssociation ? 0 : 1))
            #expect(try context.fetchCount(FetchDescriptor<ArticleDelivery>()) ==
                    (broken == .missingClaim ? 0 : 1))
            if broken != .missingClaim {
                let claim = try #require(context.fetch(FetchDescriptor<ArticleDelivery>()).first)
                #expect(claim.state == "delivered")
                #expect(claim.firstDigestId == digest.id)
            }

            let repository = DigestRepository(modelContext: ModelContext(reopened))
            let legacyCovered = try await repository.hasDigestSince(value.start)
            #expect(!legacyCovered)
            let end = value.start.addingTimeInterval(86_400)
            let reopenedStore = DeliveryStore(container: reopened)
            #expect(try reopenedStore.mayStartScheduled(
                period: "MORNING", occurrenceStart: value.start,
                occurrenceEnd: end, legacyCovered: legacyCovered))
            try reopenedStore.reconcileInterruptedLocalRuns(now: value.start.addingTimeInterval(60))
            let retry = try reopenedStore.start(trigger: TriggerType.scheduled.rawValue,
                                                period: "MORNING",
                                                at: value.start.addingTimeInterval(90))
            _ = try reopenedStore.finish(
                retry, outcome: .failed, diagnostics: GenerationDiagnostics(feeds: []),
                mode: .normal, artifactPath: nil, articles: [], claims: [],
                triggerType: .scheduled, period: "MORNING")
            let afterSecondRestart = DeliveryStore(container: try container(at: value.directory))
            try afterSecondRestart.reconcileInterruptedLocalRuns(
                now: value.start.addingTimeInterval(120))
            let finalContext = ModelContext(try container(at: value.directory))
            let originalRun = try #require(finalContext.fetch(FetchDescriptor<GenerationRun>())
                .first(where: { $0.runId == value.runId }))
            let originalDigest = try #require(finalContext.fetch(FetchDescriptor<Digest>())
                .first(where: { $0.id == value.digestId }))
            #expect(originalRun.finishedAt == interruptedAt)
            #expect(!originalDigest.isComplete)
            #expect(try !afterSecondRestart.mayStartScheduled(
                period: "MORNING", occurrenceStart: value.start,
                occurrenceEnd: end, legacyCovered: false))
            #expect(try afterSecondRestart.mayStartScheduled(
                period: "MORNING", occurrenceStart: end,
                occurrenceEnd: end.addingTimeInterval(86_400), legacyCovered: false))
        }
    }

    @Test("A usable completed digest still covers its period; a remote digest stays unchanged")
    func usableAndRemoteArtifactsArePreserved() async throws {
        let value = try fixture(nil)
        let storage = try container(at: value.directory)
        let context = ModelContext(storage)
        let remote = Digest(generatedAt: value.start.addingTimeInterval(-86_400),
                            epubFilePath: "/missing/remote.epub",
                            articleCount: 1, triggerType: .ghostwriter, isComplete: true,
                            remoteId: "remote-id", period: "MORNING")
        let remoteRun = GenerationRun(attemptSequence: 2, startedAt: value.start,
                                      trigger: TriggerType.ghostwriter.rawValue,
                                      period: "MORNING", digestId: remote.id)
        let mismatchedLocalRun = GenerationRun(attemptSequence: 3, startedAt: value.start,
                                               trigger: TriggerType.manual.rawValue,
                                               period: "manual", digestId: remote.id)
        context.insert(remote)
        context.insert(remoteRun)
        context.insert(mismatchedLocalRun)
        try context.save()

        let store = DeliveryStore(container: try container(at: value.directory))
        try store.reconcileInterruptedLocalRuns(now: value.start.addingTimeInterval(30))
        let after = ModelContext(try container(at: value.directory))
        let local = try #require(after.fetch(FetchDescriptor<Digest>())
            .first(where: { $0.id == value.digestId }))
        let localRun = try #require(after.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == value.runId }))
        let unchangedRemote = try #require(after.fetch(FetchDescriptor<Digest>())
            .first(where: { $0.id == remote.id }))
        let unchangedRemoteRun = try #require(after.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == remoteRun.runId }))
        let rejectedLocalRun = try #require(after.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == mismatchedLocalRun.runId }))
        #expect(local.isComplete)
        #expect(localRun.outcome == "complete")
        #expect(unchangedRemote.isComplete)
        #expect(unchangedRemote.errorMessage == nil)
        #expect(unchangedRemoteRun.outcome == "running")
        #expect(rejectedLocalRun.outcome == "failed")
        #expect(FileManager.default.fileExists(atPath: value.path))
        let covered = try await DigestRepository(modelContext: after).hasDigestSince(value.start)
        #expect(covered)
        #expect(try !store.mayStartScheduled(
            period: "MORNING", occurrenceStart: value.start,
            occurrenceEnd: value.start.addingTimeInterval(86_400), legacyCovered: covered))
    }
}
