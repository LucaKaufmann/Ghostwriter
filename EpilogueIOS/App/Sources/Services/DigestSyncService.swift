//
//  DigestSyncService.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain
import Data
import GhostwriterClient
import OSLog

enum DigestSyncFileError: LocalizedError {
    case invalidFilename(String)
    case incompleteArticles(String)

    var errorDescription: String? {
        switch self {
        case let .invalidFilename(filename):
            return "Invalid digest filename: \(filename)"
        case let .incompleteArticles(id):
            return "Incomplete articles for remote digest \(id)"
        }
    }
}

/// Required remote digests that could not be fully ingested. Successful siblings remain saved.
public struct DigestSyncIngestionError: LocalizedError {
    public let processedCount: Int
    public let failedRemoteIds: [String]

    public var failedCount: Int { failedRemoteIds.count }

    public var errorDescription: String? {
        "Digest sync saved \(processedCount) digest(s) and failed \(failedCount). Retry to complete the failed digests."
    }
}

/// Service responsible for syncing digests from Ghostwriter server
@MainActor
public final class DigestSyncService {
    private let settingsRepository: SettingsRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let sharedSyncBridge: SharedDigestSyncBridge
    private let planOverride: (@MainActor () async throws -> SharedDigestSyncPlan)?
    private let downloadOverride: (@MainActor (String) async throws -> Data)?
    private let articlesOverride: (@MainActor (String) async throws -> [DigestArticleData])?
    private let logger = Logger(subsystem: "com.epilogue", category: "DigestSync")
    private static let remoteEpubRetentionDays: TimeInterval = 30

    /// Directory where downloaded EPUBs are stored
    private let digestsDirectory: URL

    public init(
        settingsRepository: SettingsRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol
    ) {
        self.settingsRepository = settingsRepository
        self.digestRepository = digestRepository
        self.sharedSyncBridge = makeSharedDigestSyncBridge(
            settingsRepository: settingsRepository,
            digestRepository: digestRepository
        )
        self.planOverride = nil
        self.downloadOverride = nil
        self.articlesOverride = nil

        // Create digests directory in app's documents
        let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        self.digestsDirectory = documentsURL.appendingPathComponent("Epilogue", isDirectory: true)

        // Ensure directory exists
        try? FileManager.default.createDirectory(at: digestsDirectory, withIntermediateDirectories: true)
    }

    /// Test seam for real ingestion and persistence without a server or shared planner.
    init(
        settingsRepository: SettingsRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol,
        digestsDirectory: URL,
        plan: @escaping @MainActor () async throws -> SharedDigestSyncPlan,
        download: @escaping @MainActor (String) async throws -> Data,
        articles: @escaping @MainActor (String) async throws -> [DigestArticleData]
    ) throws {
        self.settingsRepository = settingsRepository
        self.digestRepository = digestRepository
        self.sharedSyncBridge = makeSharedDigestSyncBridge(
            settingsRepository: settingsRepository,
            digestRepository: digestRepository
        )
        self.planOverride = plan
        self.downloadOverride = download
        self.articlesOverride = articles
        self.digestsDirectory = digestsDirectory
        try FileManager.default.createDirectory(at: digestsDirectory, withIntermediateDirectories: true)
    }

    /// Sync digests from Ghostwriter server
    /// Downloads new completed digests that we don't have locally
    public func sync(tracker: SyncPerformanceTracker? = nil) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            logger.debug("Ghostwriter not configured, skipping digest sync")
            return
        }

        logger.info("Starting digest sync with Ghostwriter")
        let plan: SharedDigestSyncPlan
        if let planOverride {
            plan = try await planOverride()
        } else {
            plan = try await sharedSyncBridge.planSync()
        }
        switch plan {
        case let .combined(digests: digests, shouldDownloadEpubs: _):
            try await processCombinedPlannedDigests(digests, tracker: tracker)
        case let .legacy(digests: digests, shouldDownloadEpubs: shouldDownload):
            try await processLegacyPlannedDigests(
                digests,
                shouldDownloadEpubs: shouldDownload,
                tracker: tracker
            )
        case let .error(message: message):
            throw GhostwriterError.httpError(statusCode: 500, message: message)
        case .notConfigured:
            logger.debug("Digest sync skipped by shared planner (not configured)")
        }
    }

    /// Indexed IDs remain known even when their EPUB was never downloaded or was
    /// evicted by retention. History offers explicit downloads; sync must not undo eviction.
    public func getKnownRemoteIds() async throws -> [String] {
        return try await digestRepository.getAllRemoteIds()
    }

    /// Process digests from combined sync response.
    /// Articles are already embedded, so no separate fetch needed.
    /// Downloads EPUBs concurrently (max 3).
    public func processDigestsFromSync(_ digests: [SyncDigest], tracker: SyncPerformanceTracker? = nil) async throws {
        let shouldDownloadEpubs = try await settingsRepository.getGhostwriterDownloadEpubsOnSync()
        try await ingest(digests.map { digest in
            IngestItem(
                id: digest.id, filename: digest.filename, period: digest.period,
                articleCount: digest.articleCount, createdAt: digest.createdAt,
                completedAt: digest.completedAt, articles: digest.articles.map(Self.articleData)
            )
        }, shouldDownloadEpubs: shouldDownloadEpubs, tracker: tracker)
    }

    /// Trigger a digest generation on the server
    /// - Parameter period: The period (morning, noon, evening, manual)
    /// - Returns: The digest ID and status
    public func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        let client = try await createClient()
        let response = try await client.triggerDigest(period: period)

        logger.info("Triggered digest generation: \(response.status)")

        return response
    }

    /// Poll the status of a running digest job
    /// - Parameter digestId: The digest ID to check
    /// - Returns: The current status and progress
    public func getDigestStatus(digestId: String) async throws -> DigestStatusResponse {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        let client = try await createClient()
        return try await client.getDigestStatus(id: digestId)
    }

    /// Download an EPUB for a previously synced digest.
    /// Uses filename hint when available, otherwise resolves from server by remote ID.
    public func downloadDigestEpub(remoteId: String, filenameHint: String? = nil) async throws -> URL {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        return try await downloadDigestFile(
            remoteId: remoteId,
            format: .epub,
            filenameHint: filenameHint
        )
    }

    /// Download a PDF for a previously synced digest.
    public func downloadDigestPdf(remoteId: String, filenameHint: String? = nil) async throws -> URL {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            throw GhostwriterError.notConfigured
        }

        return try await downloadDigestFile(
            remoteId: remoteId,
            format: .pdf,
            filenameHint: filenameHint
        )
    }

    private func downloadDigestFile(
        remoteId: String,
        format: DigestFileFormat,
        filenameHint: String?
    ) async throws -> URL {
        let client = try await createClient()
        let epubFilename = try await resolveFilename(client: client, remoteId: remoteId, filenameHint: filenameHint)
        let targetFilename = convertedFilename(fromEpub: epubFilename, format: format)
        let fileData = try await client.downloadDigestById(id: remoteId, format: format)
        let localURL = try saveFile(data: fileData, filename: targetFilename)
        await CustomExportHelper.exportIfConfigured(
            fileURL: localURL,
            settingsRepository: settingsRepository
        )
        return localURL
    }

    // MARK: - Private Helpers

    private func createClient() async throws -> GhostwriterClient {
        guard let url = try await settingsRepository.getGhostwriterURL() else {
            throw GhostwriterError.notConfigured
        }

        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GhostwriterClient(baseURLString: url, apiKey: apiKey)
    }

    private func saveFile(data: Data, filename: String) throws -> URL {
        let fileURL = try digestFileURL(filename: filename)

        // Remove existing file if present
        if FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }

        try data.write(to: fileURL)
        return fileURL
    }

    private func saveEPUB(data: Data, filename: String) throws -> URL {
        try saveFile(data: data, filename: filename)
    }

    private func expectedEPUBURL(filename: String) throws -> URL {
        try digestFileURL(filename: filename)
    }

    private func digestFileURL(filename: String) throws -> URL {
        try Self.validateDigestFilename(filename)

        let directoryURL = digestsDirectory.standardizedFileURL
        let fileURL = directoryURL.appendingPathComponent(filename, isDirectory: false).standardizedFileURL
        let directoryPath = directoryURL.path
        guard fileURL.path.hasPrefix(directoryPath + "/") else {
            throw DigestSyncFileError.invalidFilename(filename)
        }
        return fileURL
    }

    nonisolated static func validateDigestFilename(_ filename: String) throws {
        guard !filename.isEmpty,
              filename == URL(fileURLWithPath: filename).lastPathComponent,
              filename != ".",
              filename != "..",
              !filename.contains("/"),
              !filename.contains("\\"),
              !filename.contains("\0") else {
            throw DigestSyncFileError.invalidFilename(filename)
        }
    }

    private func convertedFilename(fromEpub filename: String, format: DigestFileFormat) -> String {
        let stem = filename.replacingOccurrences(of: ".epub", with: "", options: [.caseInsensitive])
        return "\(stem).\(format.rawValue)"
    }

    private func resolveFilename(client: GhostwriterClient, remoteId: String, filenameHint: String?) async throws -> String {
        if let filenameHint, !filenameHint.isEmpty {
            return filenameHint
        }

        let digests = try await client.listDigests(limit: 200, offset: 0, status: "completed")
        if let matched = digests.first(where: { $0.id == remoteId }) {
            return matched.filename
        }

        throw GhostwriterError.notFound("digest \(remoteId)")
    }

    /// Remove stale downloaded EPUB files for remote digests while keeping digest records.
    private func cleanupStaleRemoteEpubFiles() async {
        do {
            let digests = try await digestRepository.getAllDigests()
            let cutoff = Date().addingTimeInterval(-(Self.remoteEpubRetentionDays * 24 * 60 * 60))
            var deletedCount = 0

            for digest in digests where digest.remoteId != nil {
                guard !digest.epubFilePath.isEmpty else { continue }

                let fileURL = URL(fileURLWithPath: digest.epubFilePath)
                guard FileManager.default.fileExists(atPath: fileURL.path) else { continue }

                let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
                let modifiedAt = attributes?[.modificationDate] as? Date
                let referenceDate = modifiedAt ?? digest.generatedAt

                guard referenceDate < cutoff else { continue }

                do {
                    try FileManager.default.removeItem(at: fileURL)
                    deletedCount += 1
                } catch {
                    logger.warning("Failed to delete stale EPUB at \(fileURL.path): \(error.localizedDescription)")
                }
            }

            if deletedCount > 0 {
                logger.info("Cleaned up \(deletedCount) stale remote EPUB files")
            }
        } catch {
            logger.warning("Failed remote EPUB cleanup: \(error.localizedDescription)")
        }
    }

    private func fetchArticles(client: GhostwriterClient, digestId: String) async throws -> [DigestArticleData] {
        let response = try await client.getDigestArticles(id: digestId)

        logger.debug("Fetched \(response.articleCount) articles for digest \(digestId)")

        return response.articles.map { article in
            DigestArticleData(
                id: article.id,
                title: article.title,
                url: article.url,
                mode: article.mode,
                wordCount: article.wordCount,
                content: article.content,
                contentHTML: article.contentHTML,
                author: article.author,
                feedTitle: article.feedTitle,
                sortOrder: article.sortOrder
            )
        }
    }

    private struct IngestItem: Sendable {
        let id: String
        let filename: String
        let period: String
        let articleCount: Int
        let createdAt: String
        let completedAt: String?
        /// Nil only for the legacy API, where articles must be fetched separately.
        let articles: [DigestArticleData]?
    }

    private enum IngestResult: Sendable {
        case saved
        case failed(String)
    }

    private static func articleData(_ article: DigestArticleResponse) -> DigestArticleData {
        DigestArticleData(
            id: article.id, title: article.title, url: article.url, mode: article.mode,
            wordCount: article.wordCount, content: article.content,
            contentHTML: article.contentHTML, author: article.author,
            feedTitle: article.feedTitle, sortOrder: article.sortOrder
        )
    }

    private static func articleData(_ article: SharedDigestSyncPlan.SyncArticle) -> DigestArticleData {
        DigestArticleData(
            id: article.id, title: article.title, url: article.url, mode: article.mode,
            wordCount: article.wordCount, content: article.content,
            contentHTML: article.contentHTML, author: article.author,
            feedTitle: article.feedTitle, sortOrder: article.sortOrder
        )
    }

    private func processLegacyPlannedDigests(
        _ digests: [SharedDigestSyncPlan.LegacyDigest],
        shouldDownloadEpubs: Bool,
        tracker: SyncPerformanceTracker?
    ) async throws {
        try await ingest(digests.map { digest in
            IngestItem(
                id: digest.id, filename: digest.filename, period: digest.period,
                articleCount: digest.articleCount, createdAt: digest.createdAt,
                completedAt: digest.completedAt, articles: nil
            )
        }, shouldDownloadEpubs: shouldDownloadEpubs, tracker: tracker)
    }

    private func processCombinedPlannedDigests(
        _ digests: [SharedDigestSyncPlan.CombinedDigest],
        tracker: SyncPerformanceTracker?
    ) async throws {
        let shouldDownloadEpubs = try await settingsRepository.getGhostwriterDownloadEpubsOnSync()
        try await ingest(digests.map { digest in
            IngestItem(
                id: digest.id, filename: digest.filename, period: digest.period,
                articleCount: digest.articleCount, createdAt: digest.createdAt,
                completedAt: digest.completedAt, articles: digest.articles.map(Self.articleData)
            )
        }, shouldDownloadEpubs: shouldDownloadEpubs, tracker: tracker)
    }

    private func ingest(
        _ digests: [IngestItem],
        shouldDownloadEpubs: Bool,
        tracker: SyncPerformanceTracker?
    ) async throws {
        try Task.checkCancellation()
        var processedCount = 0
        var failedIds: [String] = []

        if shouldDownloadEpubs {
            // Replenish one task at a time; no more than three downloads are active.
            try await withThrowingTaskGroup(of: IngestResult.self) { group in
                var iterator = digests.makeIterator()
                for _ in 0..<min(3, digests.count) {
                    if let digest = iterator.next() {
                        group.addTask { try await self.attempt(digest, shouldDownloadEpubs: true, tracker: tracker) }
                    }
                }
                do {
                    while let result = try await group.next() {
                        switch result {
                        case .saved: processedCount += 1
                        case let .failed(id): failedIds.append(id)
                        }
                        try Task.checkCancellation()
                        if let digest = iterator.next() {
                            group.addTask { try await self.attempt(digest, shouldDownloadEpubs: true, tracker: tracker) }
                        }
                    }
                } catch {
                    group.cancelAll()
                    throw error
                }
            }
        } else {
            for digest in digests {
                try Task.checkCancellation()
                switch try await attempt(digest, shouldDownloadEpubs: false, tracker: tracker) {
                case .saved: processedCount += 1
                case let .failed(id): failedIds.append(id)
                }
            }
        }

        try Task.checkCancellation()
        guard failedIds.isEmpty else {
            throw DigestSyncIngestionError(processedCount: processedCount, failedRemoteIds: failedIds)
        }
        try await settingsRepository.setLastDigestSyncTime(Date())
        await cleanupStaleRemoteEpubFiles()
        logger.info("Digest sync completed: processed \(processedCount) digests")
    }

    private func attempt(
        _ digest: IngestItem,
        shouldDownloadEpubs: Bool,
        tracker: SyncPerformanceTracker?
    ) async throws -> IngestResult {
        do {
            try Task.checkCancellation()
            try await ingestOne(digest, shouldDownloadEpubs: shouldDownloadEpubs, tracker: tracker)
            try Task.checkCancellation()
            return .saved
        } catch {
            if error is CancellationError || Task.isCancelled { throw CancellationError() }
            logger.error("Failed to ingest remote digest \(digest.id): \(error.localizedDescription)")
            return .failed(digest.id)
        }
    }

    private func ingestOne(
        _ digest: IngestItem,
        shouldDownloadEpubs: Bool,
        tracker: SyncPerformanceTracker?
    ) async throws {
        // A completed digest with no articles has no generated EPUB on the server.
        let requiresEPUB = shouldDownloadEpubs && digest.articleCount > 0
        let localURL = try expectedEPUBURL(filename: digest.filename)
        let existing = try await digestRepository.getDigestByRemoteId(digest.id)
        if let existing,
           !requiresEPUB || (!existing.epubFilePath.isEmpty &&
                             FileManager.default.fileExists(atPath: existing.epubFilePath)) {
            // The repository uses remote identity for idempotence. Retrying a mixed batch
            // must not duplicate siblings that were already committed.
            return
        }

        var articlesData = digest.articles
        if articlesData == nil {
            // Legacy metadata is incomplete until the required article request succeeds.
            // Saving it earlier would make the shared planner exclude this remote ID forever.
            if let articlesOverride {
                articlesData = try await articlesOverride(digest.id)
            } else {
                let client = try await createClient()
                articlesData = try await fetchArticles(client: client, digestId: digest.id)
            }
        }
        guard articlesData?.count == digest.articleCount else {
            throw DigestSyncFileError.incompleteArticles(digest.id)
        }
        try Task.checkCancellation()

        if requiresEPUB {
            let epubState = tracker?.beginInterval("EPUB Download [\(digest.id.prefix(8))]")
            let data: Data
            if let downloadOverride {
                data = try await downloadOverride(digest.filename)
            } else {
                let client = try await createClient()
                data = try await client.downloadDigest(filename: digest.filename)
            }
            if let epubState {
                tracker?.endInterval("EPUB Download [\(digest.id.prefix(8))]", state: epubState, bytes: data.count)
            }
            try Task.checkCancellation()
            _ = try saveEPUB(data: data, filename: digest.filename)
            await CustomExportHelper.exportIfConfigured(fileURL: localURL, settingsRepository: settingsRepository)
        }

        try Task.checkCancellation()
        if let existing {
            // A duplicate/replayed payload can supply an indexed digest again.
            // Routine planning keeps indexed IDs known, even without a local EPUB.
            existing.epubFilePath = localURL.path
            try await digestRepository.updateDigest(existing)
            return
        }
        let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()
        _ = try await digestRepository.saveRemoteDigest(
            remoteId: digest.id,
            epubFilePath: digest.articleCount > 0 ? localURL.path : "",
            articleCount: digest.articleCount,
            generatedAt: generatedAt,
            period: digest.period,
            articles: articlesData
        )
        tracker?.addArticlesSynced(articlesData?.count ?? 0)
    }
}
