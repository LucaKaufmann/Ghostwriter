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
    private let logger = Logger(subsystem: "com.epilogue", category: "DigestSync")

    /// Directory where downloaded EPUBs are stored
    private let digestsDirectory: URL

    public init(
        settingsRepository: SettingsRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol
    ) {
        self.settingsRepository = settingsRepository
        self.digestRepository = digestRepository

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

        let client = try await createClient()

        logger.info("Starting digest sync with Ghostwriter")

        // Get list of digests from server
        let remoteDigests = try await client.listDigests()
        let existingRemoteIds = Set(try await digestRepository.getAllRemoteIds())

        logger.debug("Remote digests: \(remoteDigests.count), existing: \(existingRemoteIds.count)")

        // Filter to only completed digests we don't have
        let newDigests = remoteDigests.filter { digest in
            digest.isCompleted && !existingRemoteIds.contains(digest.id)
        }

        logger.info("Found \(newDigests.count) new digests to download")

        var downloadedCount = 0

        for digest in newDigests {
            do {
                // Download EPUB
                let epubState = tracker?.beginInterval("EPUB Download [\(digest.id.prefix(8))]")
                let epubData = try await client.downloadDigest(filename: digest.filename)
                if let epubState { tracker?.endInterval("EPUB Download [\(digest.id.prefix(8))]", state: epubState, bytes: epubData.count) }

                let ioState = tracker?.beginInterval("EPUB Write [\(digest.id.prefix(8))]")
                let localURL = try saveEPUB(data: epubData, filename: digest.filename)
                if let ioState { tracker?.endInterval("EPUB Write [\(digest.id.prefix(8))]", state: ioState) }

                logger.info("Downloaded: \(localURL.lastPathComponent) (\(SyncPerformanceTracker.formatBytes(epubData.count)))")
                await CustomExportHelper.exportIfConfigured(
                    fileURL: localURL,
                    settingsRepository: settingsRepository
                )

                // Fetch articles for in-app display
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

                // Parse generation date (use server's createdAt timestamp)
                let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()
                logger.debug("Digest \(digest.id) createdAt='\(digest.createdAt)' completedAt='\(digest.completedAt ?? "nil")' parsed=\(generatedAt)")

                // Save to local database
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

                downloadedCount += 1
            } catch {
                logger.error("Failed to download digest \(digest.filename): \(error.localizedDescription)")
                // Continue with other digests
            }
        }

        // Update sync timestamp
        try await settingsRepository.setLastDigestSyncTime(Date())

        logger.info("Digest sync completed: downloaded \(downloadedCount) new digests")
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

        logger.info("Processing \(digests.count) new digests from combined sync")

        var downloadedCount = 0

        // Download EPUBs concurrently with max 3 concurrent
        await withTaskGroup(of: Bool.self) { group in
            var inFlight = 0

            for digest in digests {
                // Wait if we have 3 in flight
                if inFlight >= 3 {
                    if let success = await group.next() {
                        if success { downloadedCount += 1 }
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
                if success { downloadedCount += 1 }
            }
        }

        try await settingsRepository.setLastDigestSyncTime(Date())
        logger.info("Combined sync digest processing completed: downloaded \(downloadedCount) digests")
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

    // MARK: - Private Helpers

    private func createClient() async throws -> GhostwriterClient {
        guard let url = try await settingsRepository.getGhostwriterURL() else {
            throw GhostwriterError.notConfigured
        }

        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GhostwriterClient(baseURLString: url, apiKey: apiKey)
    }

    private func saveEPUB(data: Data, filename: String) throws -> URL {
        let fileURL = digestsDirectory.appendingPathComponent(filename)

        // Remove existing file if present
        if FileManager.default.fileExists(atPath: fileURL.path) {
            try FileManager.default.removeItem(at: fileURL)
        }

        try data.write(to: fileURL)
        return fileURL
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
                author: article.author,
                feedTitle: article.feedTitle,
                sortOrder: article.sortOrder
            )
        }
    }
}
