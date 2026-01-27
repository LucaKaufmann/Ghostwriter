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
    public func sync() async throws {
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
                let epubData = try await client.downloadDigest(filename: digest.filename)
                let localURL = try saveEPUB(data: epubData, filename: digest.filename)

                logger.info("Downloaded: \(localURL.lastPathComponent)")

                // Fetch articles for in-app display
                var articlesData: [DigestArticleData]?
                do {
                    articlesData = try await fetchArticles(client: client, digestId: digest.id)
                } catch {
                    logger.error("Failed to fetch articles for digest \(digest.id): \(error.localizedDescription)")
                }

                // Parse generation date (use server's createdAt timestamp)
                let generatedAt = digest.createdAt.toISO8601Date() ?? digest.completedAt?.toISO8601Date() ?? Date()
                logger.debug("Digest \(digest.id) createdAt='\(digest.createdAt)' completedAt='\(digest.completedAt ?? "nil")' parsed=\(generatedAt)")

                // Save to local database
                _ = try await digestRepository.saveRemoteDigest(
                    remoteId: digest.id,
                    epubFilePath: localURL.path,
                    articleCount: digest.articleCount,
                    generatedAt: generatedAt,
                    period: digest.period,
                    articles: articlesData
                )

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
