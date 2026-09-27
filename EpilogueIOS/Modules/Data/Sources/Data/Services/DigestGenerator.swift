import Foundation
import Darwin
import OSLog
import Domain
import GhostwriterClient

public struct LocalGenerationResult {
    public let runId: UUID
    public let outcome: LocalGenerationOutcome
    public let diagnostics: GenerationDiagnostics
    public let digest: Digest?
}

private actor LocalGenerationGate {
    static let shared = LocalGenerationGate()
    private var occupied = false

    func enter() -> Bool {
        guard !occupied else { return false }
        occupied = true
        return true
    }

    func leave() { occupied = false }
}

public enum DigestGeneratorError: LocalizedError {
    case alreadyGenerating
    case artifactNotDurable

    public var errorDescription: String? {
        switch self {
        case .alreadyGenerating: return "Another local edition is already being generated."
        case .artifactNotDurable: return "The edition file could not be saved safely."
        }
    }
}

/// Builds one local edition. No SwiftData model crosses an asynchronous task boundary.
@MainActor
public final class DigestGenerator {
    private let feedRepository: FeedRepositoryProtocol
    private let articleRepository: ArticleRepositoryProtocol
    private let epubBuilder: EPUBBuilderProtocol
    private let deliveryStore: DeliveryStore
    private let documentsDirectory: URL
    private let filterSignature: String
    private let logger = Logger(subsystem: "com.epilogue", category: "LocalGeneration")
    public var failAfterCommitForTesting = false

    public init(feedRepository: FeedRepositoryProtocol,
                articleRepository: ArticleRepositoryProtocol,
                epubBuilder: EPUBBuilderProtocol,
                deliveryStore: DeliveryStore,
                filterSignature: String,
                documentsDirectory: URL? = nil) {
        self.feedRepository = feedRepository
        self.articleRepository = articleRepository
        self.epubBuilder = epubBuilder
        self.deliveryStore = deliveryStore
        self.filterSignature = filterSignature
        let appDocs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        self.documentsDirectory = documentsDirectory ?? appDocs.appendingPathComponent("Epilogue")
    }

    private struct Candidate {
        let article: RawArticle
        let key: String
        let sourceIndex: Int
        let lastAttempt: Int64
    }

    /// Launch recovery does not require a feed or provider configuration.
    /// If an active generator holds the lease, its running row is not stale.
    @discardableResult
    public static func recoverInterruptedRuns(store: DeliveryStore, now: Date = Date())
        async throws -> Bool {
        guard await LocalGenerationGate.shared.enter() else { return false }
        do {
            try store.reconcileInterruptedLocalRuns(now: now)
            await LocalGenerationGate.shared.leave()
            return true
        } catch {
            await LocalGenerationGate.shared.leave()
            throw error
        }
    }

    public func generateDigest(triggerType: TriggerType, period: String? = nil,
                               mode: LocalGenerationMode = .normal,
                               now: Date = Date()) async throws -> LocalGenerationResult {
        try await withLease {
            try deliveryStore.reconcileInterruptedLocalRuns(now: now)
            return try await generate(triggerType: triggerType, period: period, mode: mode, now: now)
        }
    }

    /// Coverage, attempt budget and the new run start happen within one lease.
    /// A nil result means another accepted outcome already covers this window.
    public func generateScheduledIfEligible(period: String, occurrenceStart: Date,
                                            occurrenceEnd: Date, now: Date,
                                            legacyCovered: @MainActor () async throws -> Bool)
        async throws -> LocalGenerationResult? {
        try await withLease {
            try deliveryStore.reconcileInterruptedLocalRuns(now: now)
            let covered = try await legacyCovered()
            guard try deliveryStore.mayStartScheduled(
                period: period, occurrenceStart: occurrenceStart,
                occurrenceEnd: occurrenceEnd, legacyCovered: covered) else { return nil }
            return try await generate(triggerType: .scheduled, period: period, mode: .normal, now: now)
        }
    }

    private func withLease<T>(_ operation: () async throws -> T) async throws -> T {
        guard await LocalGenerationGate.shared.enter() else {
            throw DigestGeneratorError.alreadyGenerating
        }
        do {
            let result = try await operation()
            await LocalGenerationGate.shared.leave()
            return result
        } catch {
            await LocalGenerationGate.shared.leave()
            throw error
        }
    }

    private func generate(triggerType: TriggerType, period: String?,
                          mode: LocalGenerationMode, now: Date) async throws -> LocalGenerationResult {
        let handle = try deliveryStore.start(trigger: triggerType.rawValue, period: period,
                                             mode: mode, at: now)
        var diagnostics = GenerationDiagnostics(feeds: [], mode: mode)
        var included: [ProcessedArticle] = []
        var claims: [DeliveryClaim] = []
        var artifact: URL?

        do {
            let liveFeeds = try await feedRepository.getEnabledFeeds()
            let feeds = liveFeeds.map {
                FeedGenerationSnapshot(url: $0.url, name: $0.name,
                                       mode: $0.mode, maxArticles: $0.maxArticles)
            }
            for feed in feeds {
                try Task.checkCancellation()
                let feedFilterSignature = DeliveryFilterSignature.forFeed(
                    base: filterSignature, mode: feed.mode)
                var result = FeedIngestionResult(feedUrl: feed.url)
                let raw: [RawArticle]
                do {
                    raw = try await articleRepository.fetchFeedArticles(feedUrl: feed.url)
                } catch is CancellationError {
                    throw CancellationError()
                } catch {
                    result.feedError = "fetch_failed"
                    diagnostics.feeds.append(result)
                    continue
                }
                var seen = Set<String>()
                var candidates: [Candidate] = []
                let ledger = try deliveryStore.ledger(feedUrl: feed.url)
                for (index, source) in raw.enumerated() {
                    guard let identity = ArticleDeliveryIdentityBridge.identify(source.link) else {
                        result.failedItems.append(GenerationItemError(
                            articleKey: nil, url: source.link, stage: "identity", code: "invalid_identity"))
                        continue
                    }
                    guard seen.insert(identity.articleKey).inserted else { continue }
                    result.candidateCount += 1
                    let previous = ledger[identity.articleKey]
                    if mode == .normal && previous?.state == "delivered" { continue }
                    if mode == .normal && previous?.state == "excluded" &&
                        previous?.filterSignature == feedFilterSignature { continue }
                    candidates.append(Candidate(
                        article: RawArticle(title: source.title, link: source.link,
                                            author: source.author, publishedAt: source.publishedAt,
                                            feedUrl: feed.url, feedName: feed.name),
                        key: identity.articleKey, sourceIndex: index,
                        lastAttempt: previous?.lastAttemptSequence ?? 0))
                }
                candidates.sort {
                    if $0.lastAttempt != $1.lastAttempt {
                        return $0.lastAttempt < $1.lastAttempt
                    }
                    return $0.sourceIndex < $1.sourceIndex
                }
                let selected = feed.maxArticles > 0 ? Array(candidates.prefix(feed.maxArticles)) : candidates
                result.capDeferredCount = candidates.count - selected.count
                result.selectedCount = selected.count
                try deliveryStore.markAttempts(selected.map {
                    DeliveryClaim(feedUrl: feed.url, articleKey: $0.key, state: "retryable")
                }, run: handle)
                for candidate in selected {
                    try Task.checkCancellation()
                    do {
                        let processed = try await articleRepository.processArticle(
                            candidate.article, mode: feed.mode)
                        included.append(processed)
                        claims.append(DeliveryClaim(feedUrl: feed.url, articleKey: candidate.key,
                                                    state: "delivered",
                                                    filterSignature: feedFilterSignature))
                        result.deliveredCount += 1
                    } catch is CancellationError {
                        throw CancellationError()
                    } catch ArticleProcessingError.contentTooShort {
                        claims.append(DeliveryClaim(feedUrl: feed.url, articleKey: candidate.key,
                                                    state: "excluded", reason: "content_too_short",
                                                    filterSignature: feedFilterSignature))
                        result.filteredCount += 1
                    } catch {
                        let classification = Self.classify(error)
                        result.failedItems.append(GenerationItemError(
                            articleKey: candidate.key, url: candidate.article.link,
                            stage: classification.stage, code: classification.code))
                    }
                }
                diagnostics.feeds.append(result)
            }
            try Task.checkCancellation()
            let outcome: LocalGenerationOutcome
            if !included.isEmpty {
                outcome = diagnostics.failedCount > 0 || diagnostics.deferredCount > 0 ? .partial : .complete
            } else if diagnostics.failedCount > 0 {
                outcome = .failed
            } else if diagnostics.filteredCount > 0 && diagnostics.deferredCount > 0 {
                outcome = .deferred
            } else {
                outcome = .empty
            }
            if !included.isEmpty {
                let builder = epubBuilder
                let directory = documentsDirectory
                let snapshot = included
                let task = Task.detached(priority: .utility) {
                    try Self.makeDurableEPUB(articles: snapshot, period: period,
                                             builder: builder, directory: directory)
                }
                artifact = try await withTaskCancellationHandler {
                    try await task.value
                } onCancel: {
                    task.cancel()
                }
            }
            try Task.checkCancellation()
            let terminalClaims = outcome == .failed ? [] : claims
            let digest = try deliveryStore.finish(handle, outcome: outcome,
                                                  diagnostics: diagnostics, mode: mode,
                                                  artifactPath: artifact?.path,
                                                  articles: included,
                                                  claims: terminalClaims,
                                                  triggerType: triggerType, period: period)
            if let digest {
                do {
                    try deliveryStore.enforceRetentionPolicy(protectedDigestId: digest.id)
                } catch {
                    // Retention is post-commit housekeeping; the edition and
                    // its claim have already completed successfully.
                    logger.error("Edition retention failed: \(error.localizedDescription)")
                }
            }
            if failAfterCommitForTesting {
                failAfterCommitForTesting = false
                throw DigestGeneratorError.artifactNotDurable
            }
            return LocalGenerationResult(runId: handle.id, outcome: outcome,
                                         diagnostics: diagnostics, digest: digest)
        } catch {
            if let committed = try? deliveryStore.completedRun(handle.id),
               committed.outcome != .conflict && committed.outcome != .cancelled {
                // A failure after the DB commit cannot revoke a completed
                // edition or turn its user-visible outcome into failure.
                return LocalGenerationResult(runId: handle.id,
                                             outcome: committed.outcome,
                                             diagnostics: committed.diagnostics,
                                             digest: committed.digest)
            }
            if let artifact,
               (try? deliveryStore.committedArtifact(runId: handle.id, path: artifact.path)) == false {
                try? FileManager.default.removeItem(at: artifact)
            }
            let outcome: LocalGenerationOutcome = error is CancellationError ? .cancelled :
                error is DeliveryStoreError ? .conflict : .failed
            for index in diagnostics.feeds.indices {
                diagnostics.feeds[index].deliveredCount = 0
            }
            diagnostics.runError = outcome == .cancelled ? "cancelled" :
                outcome == .conflict ? "delivery_claim_conflict" : "generation_failed"
            // The run row is independent of a downloadable Digest. A failed
            // finalization leaves all identities retryable and records why.
            _ = try? deliveryStore.finish(handle, outcome: outcome, diagnostics: diagnostics,
                                          mode: mode, artifactPath: nil, articles: [], claims: [],
                                          triggerType: triggerType, period: period)
            throw error
        }
    }

    private static func classify(_ error: Error) -> (stage: String, code: String) {
        switch error {
        case ArticleProcessingError.extractionFailed:
            return ("extraction", "extraction_failed")
        case ArticleProcessingError.summaryFailed:
            return ("ai", "summary_failed")
        case ArticleProcessingError.aiServiceUnavailable:
            return ("ai", "not_configured")
        default:
            return ("processing", "processing_failed")
        }
    }

    nonisolated private static func makeDurableEPUB(articles: [ProcessedArticle], period: String?,
                                                    builder: EPUBBuilderProtocol, directory: URL) throws -> URL {
        try Task.checkCancellation()
        try FileManager.default.createDirectory(at: directory,
                                                withIntermediateDirectories: true)
        let token = UUID().uuidString.lowercased()
        let name = "Epilogue_\(token)" + (period.map { "_\($0.lowercased())" } ?? "") + ".epub"
        let temporary = directory.appendingPathComponent(".\(name).pending")
        let final = directory.appendingPathComponent(name)
        do {
            _ = try builder.generateEPUB(articles: articles, outputPath: temporary.path,
                                             date: Date())
            try Task.checkCancellation()
            let descriptor = open(temporary.path, O_RDONLY)
            guard descriptor >= 0 else { throw DigestGeneratorError.artifactNotDurable }
            defer { close(descriptor) }
            guard fsync(descriptor) == 0 else { throw DigestGeneratorError.artifactNotDurable }
            try FileManager.default.moveItem(at: temporary, to: final)
            let directoryDescriptor = open(directory.path, O_RDONLY)
            guard directoryDescriptor >= 0 else { throw DigestGeneratorError.artifactNotDurable }
            defer { close(directoryDescriptor) }
            guard fsync(directoryDescriptor) == 0 else { throw DigestGeneratorError.artifactNotDurable }
            try Task.checkCancellation()
            return final
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            try? FileManager.default.removeItem(at: final)
            throw error
        }
    }
}
