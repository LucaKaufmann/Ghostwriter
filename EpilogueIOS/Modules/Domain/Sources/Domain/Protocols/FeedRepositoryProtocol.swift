//
//  FeedRepositoryProtocol.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Protocol defining feed management operations.
public protocol FeedRepositoryProtocol: Sendable {
    /// Fetches all feeds from the database
    func getAllFeeds() async throws -> [Feed]

    /// Fetches all enabled feeds from the database
    func getEnabledFeeds() async throws -> [Feed]

    /// Fetches a specific feed by URL
    func getFeed(url: String) async throws -> Feed?

    /// Adds a new feed to the database
    func addFeed(_ feed: Feed) async throws

    /// Updates an existing feed
    func updateFeed(_ feed: Feed) async throws

    /// Deletes a feed by URL
    func deleteFeed(url: String) async throws

    /// Updates the last fetched timestamp for a feed
    func updateLastFetched(url: String, timestamp: Int64) async throws

    /// Checks if a feed with the given URL exists
    func feedExists(url: String) async throws -> Bool

    // MARK: - Ghostwriter Sync

    /// Upsert multiple feeds (insert or update based on URL)
    func upsertAll(_ feeds: [Feed]) async throws

    /// Delete feeds by their URLs
    func deleteByURLs(_ urls: [String]) async throws

    /// Clear the locallyModified flag for all feeds
    func clearAllLocallyModified() async throws

    /// Get all feeds that have been locally modified
    func getLocallyModifiedFeeds() async throws -> [Feed]

    /// Mark a feed as locally modified
    func markAsLocallyModified(url: String) async throws
}
