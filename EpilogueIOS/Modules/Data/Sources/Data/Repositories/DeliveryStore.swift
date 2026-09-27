import Foundation
import SwiftData
import Domain

public struct DeliveryRunHandle: Sendable {
    public let id: UUID
    public let attemptSequence: Int64
}

public struct DeliveryLedgerValue: Sendable {
    public let state: String
    public let filterSignature: String?
    public let lastAttemptSequence: Int64
}

public struct DeliveryClaim: Sendable {
    public let feedUrl: String
    public let articleKey: String
    public let state: String
    public let reason: String?
    public let filterSignature: String?

    public init(feedUrl: String, articleKey: String, state: String,
                reason: String? = nil, filterSignature: String? = nil) {
        self.feedUrl = feedUrl
        self.articleKey = articleKey
        self.state = state
        self.reason = reason
        self.filterSignature = filterSignature
    }
}

public enum DeliveryStoreError: Error {
    case alreadyDelivered, missingRun, invalidClaim, injectedSaveFailure, injectedRetentionFailure
}

/// Uses short, synchronous MainActor transactions. Independent instances and
/// contexts enter this executor one at a time; the database state check is a
/// second guard after the generation gate.
@MainActor
public final class DeliveryStore {
    private let container: ModelContainer
    public var failNextFinalSaveForTesting = false
    public var failBeforeTransactionCommitForTesting = false
    public var failNextRetentionForTesting = false

    public init(container: ModelContainer) { self.container = container }

    private func context() -> ModelContext {
        let value = ModelContext(container)
        value.autosaveEnabled = false
        return value
    }

    private func run(_ id: UUID, in context: ModelContext) throws -> GenerationRun {
        guard let value = try context.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == id }) else { throw DeliveryStoreError.missingRun }
        return value
    }

    public func start(trigger: String, period: String?) throws -> DeliveryRunHandle {
        let context = context()
        var result: DeliveryRunHandle?
        do {
            try context.transaction {
                let sequence = (try context.fetch(FetchDescriptor<GenerationRun>())
                    .map(\.attemptSequence).max() ?? 0) + 1
                let run = GenerationRun(attemptSequence: sequence, trigger: trigger, period: period)
                context.insert(run)
                try context.save()
                result = DeliveryRunHandle(id: run.runId, attemptSequence: sequence)
            }
            return result!
        } catch {
            context.rollback()
            throw error
        }
    }

    public func ledger(feedUrl: String) throws -> [String: DeliveryLedgerValue] {
        let context = context()
        return Dictionary(uniqueKeysWithValues: try context.fetch(FetchDescriptor<ArticleDelivery>())
            .filter { $0.feedUrl == feedUrl }
            .map { ($0.articleKey, DeliveryLedgerValue(state: $0.state,
                                                        filterSignature: $0.filterSignature,
                                                        lastAttemptSequence: $0.lastAttemptSequence)) })
    }

    /// Fairness markers are durable before extraction, but never count as delivery.
    public func markAttempts(_ claims: [DeliveryClaim], run handle: DeliveryRunHandle) throws {
        let context = context()
        do {
            try context.transaction {
                _ = try run(handle.id, in: context)
                let existing = Dictionary(uniqueKeysWithValues:
                    try context.fetch(FetchDescriptor<ArticleDelivery>()).map { ($0.identity, $0) })
                for claim in claims {
                    let key = ArticleDelivery(feedUrl: claim.feedUrl, articleKey: claim.articleKey)
                    if let row = existing[key.identity] {
                        row.lastAttemptSequence = handle.attemptSequence
                    } else {
                        key.lastAttemptSequence = handle.attemptSequence
                        context.insert(key)
                    }
                }
                try context.save()
            }
        } catch {
            context.rollback()
            throw error
        }
    }

    /// The only normal-delivery claim path. History, associations, ledger and
    /// diagnostic outcome share one save or roll back together.
    public func finish(_ handle: DeliveryRunHandle, outcome: LocalGenerationOutcome,
                       diagnostics: GenerationDiagnostics, mode: LocalGenerationMode,
                       artifactPath: String?, articles: [ProcessedArticle],
                       claims: [DeliveryClaim], triggerType: TriggerType,
                       period: String?) throws -> Digest? {
        let context = context()
        var result: Digest?
        do {
            try context.transaction {
                let run = try run(handle.id, in: context)
                guard run.outcome == "running" else { throw DeliveryStoreError.invalidClaim }
                let existing = Dictionary(uniqueKeysWithValues:
                    try context.fetch(FetchDescriptor<ArticleDelivery>()).map { ($0.identity, $0) })
                let deliveredClaims = claims.filter { $0.state == "delivered" }
                guard deliveredClaims.count == articles.count,
                      (artifactPath != nil) == !articles.isEmpty,
                      !([.failed, .cancelled, .conflict].contains(outcome) && !claims.isEmpty) else {
                    throw DeliveryStoreError.invalidClaim
                }
                var digest: Digest?
                if let artifactPath {
                    let fileSize = try FileManager.default.attributesOfItem(atPath: artifactPath)[.size] as? Int64 ?? 0
                    let created = Digest(epubFilePath: artifactPath,
                                         articleCount: articles.count,
                                         briefingCount: articles.filter(\.isSummary).count,
                                         deepDiveCount: articles.filter { !$0.isSummary }.count,
                                         triggerType: triggerType, fileSizeBytes: fileSize,
                                         isComplete: true, period: period)
                    context.insert(created)
                    for (index, article) in articles.enumerated() {
                        let association = article.toDigestArticle(
                            contentType: article.isSummary ? .briefing : .deepDive,
                            orderIndex: index)
                        association.digest = created
                        context.insert(association)
                    }
                    digest = created
                }
                for claim in claims {
                    guard claim.state == "delivered" || claim.state == "excluded" else {
                        throw DeliveryStoreError.invalidClaim
                    }
                    let key = ArticleDelivery(feedUrl: claim.feedUrl, articleKey: claim.articleKey)
                    let prior = existing[key.identity]
                    if prior?.state == "delivered" {
                        if mode == .normal { throw DeliveryStoreError.alreadyDelivered }
                        // Regeneration never changes the first normal claim.
                        continue
                    }
                    if mode == .normal, prior?.state == "excluded",
                       prior?.filterSignature == claim.filterSignature {
                        throw DeliveryStoreError.invalidClaim
                    }
                    let row = prior ?? key
                    if prior == nil { context.insert(row) }
                    row.state = claim.state
                    row.reason = claim.state == "excluded" ? claim.reason : nil
                    row.filterSignature = claim.state == "excluded" ? claim.filterSignature : nil
                    if claim.state == "delivered" {
                        row.firstDigestId = digest?.id
                        row.committedAt = Date()
                    }
                }
                run.outcome = outcome.rawValue
                run.finishedAt = Date()
                run.digestId = digest?.id
                run.diagnosticsJSON = String(data: try JSONEncoder().encode(diagnostics),
                                             encoding: .utf8) ?? "{}"
                if failNextFinalSaveForTesting {
                    failNextFinalSaveForTesting = false
                    throw DeliveryStoreError.injectedSaveFailure
                }
                if failBeforeTransactionCommitForTesting {
                    failBeforeTransactionCommitForTesting = false
                    throw DeliveryStoreError.injectedSaveFailure
                }
                result = digest
            }
            return result
        } catch {
            context.rollback()
            throw error
        }
    }

    public func latestRun() throws -> GenerationRun? {
        try context().fetch(FetchDescriptor<GenerationRun>()).max {
            $0.attemptSequence < $1.attemptSequence
        }
    }

    public func committedArtifact(runId: UUID, path: String) throws -> Bool {
        let context = context()
        guard let run = try context.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == runId }),
              let digestId = run.digestId,
              ["complete", "partial"].contains(run.outcome) else { return false }
        return try context.fetch(FetchDescriptor<Digest>()).contains {
            $0.id == digestId && $0.epubFilePath == path && $0.isComplete
        }
    }

    public func completedRun(_ id: UUID) throws -> (outcome: LocalGenerationOutcome,
                                                    diagnostics: GenerationDiagnostics,
                                                    digest: Digest?)? {
        let context = context()
        guard let run = try context.fetch(FetchDescriptor<GenerationRun>())
            .first(where: { $0.runId == id }),
              let outcome = LocalGenerationOutcome(rawValue: run.outcome) else { return nil }
        let diagnostics = (try? JSONDecoder().decode(
            GenerationDiagnostics.self, from: Data(run.diagnosticsJSON.utf8))) ??
            GenerationDiagnostics(feeds: [])
        let digest = try context.fetch(FetchDescriptor<Digest>())
            .first(where: { $0.id == run.digestId })
        return (outcome, diagnostics, digest)
    }

    public func hasTerminalScheduledRun(period: String, since start: Date) throws -> Bool {
        try context().fetch(FetchDescriptor<GenerationRun>()).contains {
            $0.trigger == TriggerType.scheduled.rawValue && $0.period == period &&
            $0.startedAt >= start &&
            ["complete", "partial", "empty", "deferred"].contains($0.outcome)
        }
    }

    /// Reuse the existing history/file retention policy after a successful
    /// delivery transaction. A cleanup failure cannot revoke that delivery.
    public func enforceRetentionPolicy(protectedDigestId: UUID) throws {
        let failBeforeCommit = failNextRetentionForTesting
        failNextRetentionForTesting = false
        let repository = DigestRepository(modelContext: context())
        try repository.enforceRetentionPolicy(maxDigests: 30,
                                             protectedDigestId: protectedDigestId,
                                             failBeforeCommitForTesting: failBeforeCommit)
    }
}
