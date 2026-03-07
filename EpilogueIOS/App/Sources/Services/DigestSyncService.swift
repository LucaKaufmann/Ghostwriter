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

/// Service responsible for syncing digests from Ghostwriter server
@MainActor
public final class DigestSyncService {
    private let settingsRepository: SettingsRepositoryProtocol
    private let digestRepository: DigestRepositoryProtocol
    private let sharedSyncBridge: SharedDigestSyncBridge
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

        // Create digests directory in app's documents
        let documentsURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        self.digestsDirectory = documentsURL.appendingPathComponent("Epilogue", isDirectory: true)

        // Ensure directory exists
        try? FileManager.default.createDirectory(at: digestsDirectory, withIntermediateDirectories: true)
    }

    /// Sync digests from Ghostwriter server
    /// Downloads new completed digests that we don't have locally
    public func sync(tracker: SyncPerformanceTracker? = nil) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            logger.debug("Ghostwriter not configured, skipping digest sync")
            return
        }

        logger.info("Starting digest sync with Ghostwriter")
        let plan = try await sharedSyncBridge.planSync()
        switch plan {
        case let .combined(digests: digests, shouldDownloadEpubs: _):
            try await processDigestsFromSync(digests, tracker: tracker)
        case let .legacy(digests: digests, shouldDownloadEpubs: shouldDownload):
            try await processLegacyDigests(
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

    /// Get all known remote digest IDs from local database
    public func getKnownRemoteIds() async throws -> [String] {
        return try await digestRepository.getAllRemoteIds()
    }

    /// Process digests from combined sync response.
    /// Articles are already embedded, so no separate fetch needed.
    /// Downloads EPUBs concurrently (max 3).
    public func processDigestsFromSync(_ digests: [SyncDigest], tracker: SyncPerformanceTracker? = nil) async throws {
        guard !digests.isEmpty else {
            logger.info("No new digests from combined sync")
            return
        }

        let shouldDownloadEpubs = try await settingsRepository.getGhostwriterDownloadEpubsOnSync()
        logger.info(
            "Processing \(digests.count) new digests from combined sync \(shouldDownloadEpubs ? "with EPUB download" : "without EPUB download")"
        )

        var processedCount = 0

        if shouldDownloadEpubs {
            // Download EPUBs concurrently with max 3 concurrent
            await withTaskGroup(of: Bool.self) { group in
                var inFlight = 0

                for digest in digests {
                    // Wait if we have 3 in flight
                    if inFlight >= 3 {
                        if let success = await group.next() {
                            if success { processedCount += 1 }
                            inFlight -= 1
                        }
                    }

                    inFlight += 1
                    group.addTask { [self] in
                        await self.downloadAndSaveFromSync(digest, tracker: tracker)
                    }
                }

                // Collect remaining
                for await success in group {
                    if success { processedCount += 1 }
                }
            }
        } else {
            for digest in digests {
                if await saveFromSyncWithoutDownload(digest, tracker: tracker) {
                    processedCount += 1
                }
            }
        }

        try await settingsRepository.setLastDigestSyncTime(Date())
        await cleanupStaleRemoteEpubFiles()
        logger.info("Combined sync digest processing completed: processed \(processedCount) digests")
    }

    /// Download a single digest from sync data and save it.
    private func downloadAndSaveFromSync(_ digest: SyncDigest, tracker: SyncPerformanceTracker? = nil) async -> Bool {
        do {
            let client = try await createClient()

            let epubState = tracker?.beginInterval("EPUB Download [\(digest.id.prefix(8))]")
            let epubData = try await client.downloadDigest(filename: digest.filename)
            if let epubState { tracker?.endInterval("EPUB Download [\(digest.id.prefix(8))]", state: epubState, bytes: epubData.count) }

            let ioState = tracker?.beginInterval("EPUB Write [\(digest.id.prefix(8))]")
            let localURL = try saveEPUB(data: epubData, filename: digest.filename)
            if let ioState { tracker?.endInterval("EPUB Write [\(digest.id.prefix(8))]", state: ioState) }
            await CustomExportHelper.exportIfConfigured(
                fileURL: localURL,
                settingsRepository: settingsRepository
            )

            let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()

            // Articles are already embedded in the sync response
            let articlesData: [DigestArticleData]? = digest.articles.isEmpty ? nil : digest.articles.map { article in
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

            if let articlesData { tracker?.addArticlesSynced(articlesData.count) }

            let saveState = tracker?.beginInterval("DB Save [\(digest.id.prefix(8))]")
            _ = try await digestRepository.saveRemoteDigest(
                remoteId: digest.id,
                epubFilePath: localURL.path,
                articleCount: digest.articleCount,
                generatedAt: generatedAt,
                period: digest.period,
                articles: articlesData
            )
            if let saveState { tracker?.endInterval("DB Save [\(digest.id.prefix(8))]", state: saveState) }

            logger.info("Downloaded and saved digest \(digest.id) from combined sync (\(SyncPerformanceTracker.formatBytes(epubData.count)))")
            return true
        } catch {
            logger.error("Failed to download digest \(digest.filename) from sync: \(error.localizedDescription)")
            return false
        }
    }

    /// Save a synced digest and embedded articles without downloading the EPUB.
    private func saveFromSyncWithoutDownload(_ digest: SyncDigest, tracker: SyncPerformanceTracker? = nil) async -> Bool {
        do {
            let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()
            let localURL = expectedEPUBURL(filename: digest.filename)

            let articlesData: [DigestArticleData]? = digest.articles.isEmpty ? nil : digest.articles.map { article in
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

            if let articlesData { tracker?.addArticlesSynced(articlesData.count) }

            let saveState = tracker?.beginInterval("DB Save [\(digest.id.prefix(8))]")
            _ = try await digestRepository.saveRemoteDigest(
                remoteId: digest.id,
                epubFilePath: localURL.path,
                articleCount: digest.articleCount,
                generatedAt: generatedAt,
                period: digest.period,
                articles: articlesData
            )
            if let saveState { tracker?.endInterval("DB Save [\(digest.id.prefix(8))]", state: saveState) }
            logger.info("Indexed digest \(digest.id) without EPUB download")
            return true
        } catch {
            logger.error("Failed to save digest \(digest.id) without EPUB download: \(error.localizedDescription)")
            return false
        }
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
        let fileURL = digestsDirectory.appendingPathComponent(filename)

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

    private func expectedEPUBURL(filename: String) -> URL {
        digestsDirectory.appendingPathComponent(filename)
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

    private func processLegacyDigests(
        _ remoteDigests: [DigestResponse],
        shouldDownloadEpubs: Bool,
        tracker: SyncPerformanceTracker?
    ) async throws {
        let client = try await createClient()
        logger.info(
            "Found \(remoteDigests.count) legacy digests \(shouldDownloadEpubs ? "to download" : "to index without download")"
        )

        var processedCount = 0
        for digest in remoteDigests {
            do {
                let localURL: URL
                if shouldDownloadEpubs {
                    let epubState = tracker?.beginInterval("EPUB Download [\(digest.id.prefix(8))]")
                    let epubData = try await client.downloadDigest(filename: digest.filename)
                    if let epubState {
                        tracker?.endInterval("EPUB Download [\(digest.id.prefix(8))]", state: epubState, bytes: epubData.count)
                    }

                    let ioState = tracker?.beginInterval("EPUB Write [\(digest.id.prefix(8))]")
                    localURL = try saveEPUB(data: epubData, filename: digest.filename)
                    if let ioState { tracker?.endInterval("EPUB Write [\(digest.id.prefix(8))]", state: ioState) }

                    logger.info("Downloaded: \(localURL.lastPathComponent) (\(SyncPerformanceTracker.formatBytes(epubData.count)))")
                    await CustomExportHelper.exportIfConfigured(
                        fileURL: localURL,
                        settingsRepository: settingsRepository
                    )
                } else {
                    localURL = expectedEPUBURL(filename: digest.filename)
                    logger.info("Indexed digest without EPUB download: \(digest.id)")
                }

                var articlesData: [DigestArticleData]?
                do {
                    let artState = tracker?.beginInterval("Articles Fetch [\(digest.id.prefix(8))]")
                    articlesData = try await fetchArticles(client: client, digestId: digest.id)
                    if let artState {
                        tracker?.endInterval("Articles Fetch [\(digest.id.prefix(8))]", state: artState)
                        tracker?.addArticlesSynced(articlesData?.count ?? 0)
                    }
                } catch {
                    logger.error("Failed to fetch articles for digest \(digest.id): \(error.localizedDescription)")
                }

                let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()
                let saveState = tracker?.beginInterval("DB Save [\(digest.id.prefix(8))]")
                _ = try await digestRepository.saveRemoteDigest(
                    remoteId: digest.id,
                    epubFilePath: localURL.path,
                    articleCount: digest.articleCount,
                    generatedAt: generatedAt,
                    period: digest.period,
                    articles: articlesData
                )
                if let saveState { tracker?.endInterval("DB Save [\(digest.id.prefix(8))]", state: saveState) }
                processedCount += 1
            } catch {
                logger.error("Failed to process digest \(digest.filename): \(error.localizedDescription)")
            }
        }

        try await settingsRepository.setLastDigestSyncTime(Date())
        await cleanupStaleRemoteEpubFiles()
        logger.info("Digest sync completed: processed \(processedCount) legacy digests")
    }
}
