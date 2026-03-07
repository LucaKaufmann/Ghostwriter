//
//  FeedSyncService.swift
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

/// Service responsible for bi-directional feed sync with Ghostwriter
/// 
/// Sync flow:
/// 1. PUSH: Local feeds → Server (additive merge)
/// 2. PULL: Server changes → Local (with tombstones)
/// 3. Clear locallyModified flags
/// 4. Update sync timestamp
@MainActor
public final class FeedSyncService {
    private let settingsRepository: SettingsRepositoryProtocol
    private let feedRepository: FeedRepositoryProtocol
    private let sharedSyncBridge: SharedFeedSyncBridge
    private let logger = Logger(subsystem: "com.epilogue", category: "FeedSync")

    public init(
        settingsRepository: SettingsRepositoryProtocol,
        feedRepository: FeedRepositoryProtocol
    ) {
        self.settingsRepository = settingsRepository
        self.feedRepository = feedRepository
        self.sharedSyncBridge = makeSharedFeedSyncBridge(
            settingsRepository: settingsRepository,
            feedRepository: feedRepository
        )
    }

    /// Perform bi-directional feed sync with Ghostwriter
    public func sync(tracker: SyncPerformanceTracker? = nil) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            logger.debug("Ghostwriter not configured, skipping feed sync")
            return
        }

        logger.info("Starting feed sync with Ghostwriter")
        let syncState = tracker?.beginInterval("Feed Sync (shared)")
        let outcome = try await sharedSyncBridge.sync()
        if let syncState { tracker?.endInterval("Feed Sync (shared)", state: syncState) }

        switch outcome {
        case let .success(pushed, updatedFeeds, deletedFeeds):
            logger.info(
                "Feed sync completed: pushed=\(pushed), updated=\(updatedFeeds), deleted=\(deletedFeeds)"
            )
        case let .error(message):
            throw GhostwriterError.httpError(statusCode: 500, message: message)
        case .notConfigured:
            logger.debug("Ghostwriter not configured, skipping feed sync")
        }
    }

    /// Push local feeds to the server
    public func pushLocalFeeds(client: GhostwriterClient? = nil, tracker: SyncPerformanceTracker? = nil) async throws {
        let ghostwriterClient: GhostwriterClient
        if let client {
            ghostwriterClient = client
        } else {
            ghostwriterClient = try await createClient()
        }

        let localFeeds = try await feedRepository.getAllFeeds()

        // Filter out synthetic feeds (wallabag, newsletters) - these are server-side integrations
        let realFeeds = localFeeds.filter { !$0.url.hasPrefix("synthetic://") }

        guard !realFeeds.isEmpty else {
            logger.debug("No local feeds to push")
            return
        }

        let syncRequests = realFeeds.map { feed -> FeedSyncRequest in
            FeedSyncRequest(
                url: feed.url,
                title: feed.name,
                isActive: feed.isEnabled,
                mode: feed.mode == .briefing ? "summarize" : "raw",
                maxArticles: feed.maxArticles > 0 ? feed.maxArticles : 10
            )
        }

        let pushState = tracker?.beginInterval("Feed Push Request")
        let result = try await ghostwriterClient.syncFeeds(syncRequests)
        if let pushState { tracker?.endInterval("Feed Push Request", state: pushState) }
        logger.info("Pushed \(result.synced) feeds to server (created: \(result.created), updated: \(result.updated), count: \(syncRequests.count))")
    }

    /// Apply feed changes from a pre-fetched sync response (combined sync endpoint).
    /// Skips the push phase (assumed already done) and the fetch.
    public func applyFeedChanges(_ changes: FeedChangesResponse) async throws {
        // Apply server feeds locally
        if !changes.feeds.isEmpty {
            let serverFeeds = changes.feeds.map { convertResponseToFeed($0) }
            logger.info("Applying \(serverFeeds.count) feeds from combined sync")
            try await feedRepository.upsertAll(serverFeeds)
        }

        // Apply tombstones
        if !changes.tombstones.isEmpty {
            let tombstoneURLs = changes.tombstones.map { $0.url }
            logger.info("Applying \(tombstoneURLs.count) tombstones from combined sync")
            try await feedRepository.deleteByURLs(tombstoneURLs)
        }

        // Clear modified flags and update timestamp
        try await feedRepository.clearAllLocallyModified()

        if let serverTime = changes.serverTimestamp.toISO8601Date() {
            try await settingsRepository.setLastFeedSyncTime(serverTime)
        } else {
            try await settingsRepository.setLastFeedSyncTime(Date())
        }

        logger.info("Applied feed changes from combined sync")
    }

    /// Notify server when a feed is deleted locally
    public func notifyFeedDeleted(url: String) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            return
        }

        let client = try await createClient()

        do {
            try await client.deleteFeed(byURL: url)
            logger.info("Notified server of feed deletion: \(url)")
        } catch GhostwriterError.notFound {
            // Feed doesn't exist on server, that's fine
            logger.debug("Feed not found on server (already deleted?): \(url)")
        }
    }

    // MARK: - Private Helpers

    private func createClient() async throws -> GhostwriterClient {
        guard let url = try await settingsRepository.getGhostwriterURL() else {
            throw GhostwriterError.notConfigured
        }

        let apiKey = try await settingsRepository.getGhostwriterAPIKey()
        return try GhostwriterClient(baseURLString: url, apiKey: apiKey)
    }

    private func convertResponseToFeed(_ response: FeedResponse) -> Feed {
        let mode: ProcessingMode = response.mode == "summarize" ? .briefing : .fidelity
        let serverUpdatedAt = response.updatedAt.toISO8601Date()

        return Feed(
            url: response.url,
            name: response.title,
            mode: mode,
            maxArticles: response.maxArticles,
            isEnabled: response.isActive,
            serverUpdatedAt: serverUpdatedAt,
            locallyModified: false
        )
    }
}
