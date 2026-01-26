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

    /// Deletes digests older than the specified count limit
    /// Used to enforce the 30-digest retention policy
    func enforceRetentionPolicy(maxDigests: Int) async throws
}
