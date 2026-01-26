//
//  DigestRepository.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData
import Domain

/// SwiftData implementation of DigestRepositoryProtocol with 30-digest retention policy
public final class DigestRepository: DigestRepositoryProtocol {
    private let modelContext: ModelContext
    private let maxDigests: Int

    /// Initialize with model context and retention limit
    /// - Parameters:
    ///   - modelContext: SwiftData model context
    ///   - maxDigests: Maximum number of digests to retain (default: 30)
    public init(modelContext: ModelContext, maxDigests: Int = 30) {
        self.modelContext = modelContext
        self.maxDigests = maxDigests
    }

    public func getAllDigests() async throws -> [Digest] {
        let descriptor = FetchDescriptor<Digest>(
            sortBy: [SortDescriptor(\.generatedAt, order: .reverse)]
        )
        return try modelContext.fetch(descriptor)
    }

    public func getDigest(id: UUID) async throws -> Digest? {
        let descriptor = FetchDescriptor<Digest>(
            predicate: #Predicate { $0.id == id }
        )
        return try modelContext.fetch(descriptor).first
    }

    public func createDigest(_ digest: Digest) async throws {
        modelContext.insert(digest)
        try modelContext.save()

        // Enforce retention policy after creating new digest
        try await enforceRetentionPolicy(maxDigests: maxDigests)
    }

    public func updateDigest(_ digest: Digest) async throws {
        // Digest is already tracked by the context, just save
        try modelContext.save()
    }

    public func deleteDigest(id: UUID) async throws {
        guard let digest = try await getDigest(id: id) else {
            throw DigestRepositoryError.digestNotFound
        }

        // Delete EPUB file from disk
        try deleteEPUBFile(at: digest.epubFilePath)

        // Delete from database (cascade will delete articles)
        modelContext.delete(digest)
        try modelContext.save()
    }

    public func deleteDigests(ids: [UUID]) async throws {
        for id in ids {
            try await deleteDigest(id: id)
        }
    }

    public func getDigests(from startDate: Date, to endDate: Date) async throws -> [Digest] {
        let descriptor = FetchDescriptor<Digest>(
            predicate: #Predicate { digest in
                digest.generatedAt >= startDate && digest.generatedAt <= endDate
            },
            sortBy: [SortDescriptor(\.generatedAt, order: .reverse)]
        )
        return try modelContext.fetch(descriptor)
    }

    public func getDigestCount() async throws -> Int {
        let descriptor = FetchDescriptor<Digest>()
        return try modelContext.fetchCount(descriptor)
    }

    public func enforceRetentionPolicy(maxDigests: Int) async throws {
        let count = try await getDigestCount()

        guard count > maxDigests else {
            return // Within limit, no action needed
        }

        // Fetch all digests sorted by date (oldest last)
        let descriptor = FetchDescriptor<Digest>(
            sortBy: [SortDescriptor(\.generatedAt, order: .reverse)]
        )
        let allDigests = try modelContext.fetch(descriptor)

        // Calculate how many to delete
        let deleteCount = count - maxDigests
        let digestsToDelete = Array(allDigests.suffix(deleteCount))

        // Delete oldest digests
        for digest in digestsToDelete {
            // Delete EPUB file from disk
            try? deleteEPUBFile(at: digest.epubFilePath)

            // Delete from database
            modelContext.delete(digest)
        }

        try modelContext.save()
    }

    // MARK: - Ghostwriter Sync

    public func getAllRemoteIds() async throws -> [String] {
        let descriptor = FetchDescriptor<Digest>(
            predicate: #Predicate { $0.remoteId != nil }
        )
        let digests = try modelContext.fetch(descriptor)
        return digests.compactMap { $0.remoteId }
    }

    public func getDigestByRemoteId(_ remoteId: String) async throws -> Digest? {
        let descriptor = FetchDescriptor<Digest>(
            predicate: #Predicate { $0.remoteId == remoteId }
        )
        return try modelContext.fetch(descriptor).first
    }

    public func saveRemoteDigest(
        remoteId: String,
        epubFilePath: String,
        articleCount: Int,
        generatedAt: Date,
        period: String,
        articles: [DigestArticleData]?
    ) async throws -> Digest {
        // Check if digest with this remote ID already exists
        if let existingDigest = try await getDigestByRemoteId(remoteId) {
            return existingDigest
        }

        // Create new digest
        let digest = Digest(
            generatedAt: generatedAt,
            epubFilePath: epubFilePath,
            articleCount: articleCount,
            briefingCount: 0, // Will be calculated if we have articles
            deepDiveCount: 0, // Will be calculated if we have articles
            triggerType: .ghostwriter,
            isComplete: true,
            remoteId: remoteId,
            period: period
        )

        // Add articles if provided
        if let articlesData = articles {
            var briefingCount = 0
            var deepDiveCount = 0

            for articleData in articlesData {
                let article = DigestArticle(
                    title: articleData.title,
                    url: articleData.url,
                    content: articleData.content,
                    wordCount: articleData.wordCount,
                    mode: articleData.mode == "summarize" ? .briefing : .fidelity,
                    feedName: articleData.feedTitle,
                    author: articleData.author
                )

                if articleData.mode == "summarize" {
                    briefingCount += 1
                } else {
                    deepDiveCount += 1
                }

                digest.articles.append(article)
            }

            digest.briefingCount = briefingCount
            digest.deepDiveCount = deepDiveCount
        }

        modelContext.insert(digest)
        try modelContext.save()

        // Enforce retention policy
        try await enforceRetentionPolicy(maxDigests: maxDigests)

        return digest
    }

    // MARK: - Private Helpers

    private func deleteEPUBFile(at path: String) throws {
        let fileURL = URL(fileURLWithPath: path)

        guard FileManager.default.fileExists(atPath: path) else {
            // File doesn't exist, nothing to delete
            return
        }

        try FileManager.default.removeItem(at: fileURL)
    }
}

// MARK: - Errors

public enum DigestRepositoryError: LocalizedError {
    case digestNotFound
    case fileOperationFailed(String)

    public var errorDescription: String? {
        switch self {
        case .digestNotFound:
            return "Digest not found"
        case .fileOperationFailed(let message):
            return "File operation failed: \(message)"
        }
    }
}
