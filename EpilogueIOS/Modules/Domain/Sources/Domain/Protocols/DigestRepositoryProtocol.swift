//
//  DigestRepositoryProtocol.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Protocol defining digest management operations.
/// Implements 30-digest retention policy.
public protocol DigestRepositoryProtocol: Sendable {
    /// Fetches all digests sorted by generation date (newest first)
    func getAllDigests() async throws -> [Digest]

    /// Fetches a specific digest by ID
    func getDigest(id: UUID) async throws -> Digest?

    /// Creates a new digest
    /// Automatically enforces 30-digest retention limit by deleting oldest digests
    func createDigest(_ digest: Digest) async throws

    /// Updates an existing digest
    func updateDigest(_ digest: Digest) async throws

    /// Deletes a digest by ID
    /// Also deletes the associated EPUB file from disk
    func deleteDigest(id: UUID) async throws

    /// Deletes multiple digests by IDs
    func deleteDigests(ids: [UUID]) async throws

    /// Fetches digests within a date range
    func getDigests(from startDate: Date, to endDate: Date) async throws -> [Digest]

    /// Gets the count of stored digests
    func getDigestCount() async throws -> Int

    /// Returns true if a completed digest exists since the given date
    func hasDigestSince(_ date: Date) async throws -> Bool

    /// Deletes digests older than the specified count limit
    /// Used to enforce the 30-digest retention policy
    func enforceRetentionPolicy(maxDigests: Int) async throws

    // MARK: - Ghostwriter Sync

    /// Get all remote IDs of digests synced from Ghostwriter
    func getAllRemoteIds() async throws -> [String]

    /// Get a digest by its remote ID
    func getDigestByRemoteId(_ remoteId: String) async throws -> Digest?

    /// Save a digest that was synced from Ghostwriter
    func saveRemoteDigest(
        remoteId: String,
        epubFilePath: String,
        articleCount: Int,
        generatedAt: Date,
        period: String,
        articles: [DigestArticleData]?
    ) async throws -> Digest
}

/// Data transfer object for digest articles from Ghostwriter
public struct DigestArticleData: Sendable {
    public let id: String
    public let title: String
    public let url: String
    public let mode: String
    public let wordCount: Int
    public let content: String
    public let contentHTML: String?
    public let author: String?
    public let feedTitle: String
    public let sortOrder: Int

    public init(
        id: String,
        title: String,
        url: String,
        mode: String,
        wordCount: Int,
        content: String,
        contentHTML: String? = nil,
        author: String?,
        feedTitle: String,
        sortOrder: Int
    ) {
        self.id = id
        self.title = title
        self.url = url
        self.mode = mode
        self.wordCount = wordCount
        self.content = content
        self.contentHTML = contentHTML
        self.author = author
        self.feedTitle = feedTitle
        self.sortOrder = sortOrder
    }
}
