//
//  FeedRepository.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData
import Domain

/// SwiftData implementation of FeedRepositoryProtocol
public final class FeedRepository: FeedRepositoryProtocol {
    private let modelContext: ModelContext

    public init(modelContext: ModelContext) {
        self.modelContext = modelContext
    }

    public func getAllFeeds() async throws -> [Feed] {
        let descriptor = FetchDescriptor<Feed>(
            sortBy: [SortDescriptor(\.createdAt, order: .reverse)]
        )
        return try modelContext.fetch(descriptor)
    }

    public func getEnabledFeeds() async throws -> [Feed] {
        let descriptor = FetchDescriptor<Feed>(
            predicate: #Predicate { $0.isEnabled == true },
            sortBy: [SortDescriptor(\.createdAt, order: .reverse)]
        )
        return try modelContext.fetch(descriptor)
    }

    public func getFeed(url: String) async throws -> Feed? {
        let descriptor = FetchDescriptor<Feed>(
            predicate: #Predicate { $0.url == url }
        )
        return try modelContext.fetch(descriptor).first
    }

    public func addFeed(_ feed: Feed) async throws {
        // Check if feed already exists
        if try await feedExists(url: feed.url) {
            throw FeedRepositoryError.feedAlreadyExists
        }

        modelContext.insert(feed)
        try modelContext.save()
    }

    public func updateFeed(_ feed: Feed) async throws {
        // Feed is already tracked by the context, just save
        try modelContext.save()
    }

    public func deleteFeed(url: String) async throws {
        guard let feed = try await getFeed(url: url) else {
            throw FeedRepositoryError.feedNotFound
        }

        modelContext.delete(feed)
        try modelContext.save()
    }

    public func updateLastFetched(url: String, timestamp: Int64) async throws {
        guard let feed = try await getFeed(url: url) else {
            throw FeedRepositoryError.feedNotFound
        }

        feed.lastFetched = timestamp
        try modelContext.save()
    }

    public func feedExists(url: String) async throws -> Bool {
        let descriptor = FetchDescriptor<Feed>(
            predicate: #Predicate { $0.url == url }
        )
        let count = try modelContext.fetchCount(descriptor)
        return count > 0
    }

    // MARK: - Ghostwriter Sync

    public func upsertAll(_ feeds: [Feed]) async throws {
        for feed in feeds {
            if let existingFeed = try await getFeed(url: feed.url) {
                // Update existing feed
                existingFeed.name = feed.name
                existingFeed.mode = feed.mode
                existingFeed.maxArticles = feed.maxArticles
                existingFeed.isEnabled = feed.isEnabled
                existingFeed.serverUpdatedAt = feed.serverUpdatedAt
                existingFeed.locallyModified = feed.locallyModified
            } else {
                // Insert new feed
                modelContext.insert(feed)
            }
        }
        try modelContext.save()
    }

    public func deleteByURLs(_ urls: [String]) async throws {
        for url in urls {
            if let feed = try await getFeed(url: url) {
                modelContext.delete(feed)
            }
        }
        try modelContext.save()
    }

    public func clearAllLocallyModified() async throws {
        let descriptor = FetchDescriptor<Feed>(
            predicate: #Predicate { $0.locallyModified == true }
        )
        let feeds = try modelContext.fetch(descriptor)

        for feed in feeds {
            feed.locallyModified = false
        }
        try modelContext.save()
    }

    public func getLocallyModifiedFeeds() async throws -> [Feed] {
        let descriptor = FetchDescriptor<Feed>(
            predicate: #Predicate { $0.locallyModified == true }
        )
        return try modelContext.fetch(descriptor)
    }

    public func markAsLocallyModified(url: String) async throws {
        guard let feed = try await getFeed(url: url) else {
            throw FeedRepositoryError.feedNotFound
        }

        feed.locallyModified = true
        try modelContext.save()
    }
}

// MARK: - Errors

public enum FeedRepositoryError: LocalizedError {
    case feedNotFound
    case feedAlreadyExists

    public var errorDescription: String? {
        switch self {
        case .feedNotFound:
            return "Feed not found"
        case .feedAlreadyExists:
            return "Feed with this URL already exists"
        }
    }
}
