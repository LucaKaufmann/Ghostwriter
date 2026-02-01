//
//  GhostwriterSyncCoordinator.swift
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

/// Coordinates all Ghostwriter sync operations
///
/// This is the main entry point for syncing with Ghostwriter.
/// Call `performFullSync()` on app launch or when the user triggers a sync.
@MainActor
public final class GhostwriterSyncCoordinator: ObservableObject {
    private let feedSyncService: FeedSyncService
    private let digestSyncService: DigestSyncService
    private let configSyncManager: ConfigSyncManager
    private let heartbeatService: HeartbeatService
    private let settingsRepository: SettingsRepositoryProtocol
    private let logger = Logger(subsystem: "com.epilogue", category: "GhostwriterSync")

    @Published public private(set) var isSyncing = false
    @Published public private(set) var lastSyncError: Error?
    @Published public private(set) var lastSyncTime: Date?

    public init(
        settingsRepository: SettingsRepositoryProtocol,
        feedRepository: FeedRepositoryProtocol,
        digestRepository: DigestRepositoryProtocol
    ) {
        self.settingsRepository = settingsRepository

        self.feedSyncService = FeedSyncService(
            settingsRepository: settingsRepository,
            feedRepository: feedRepository
        )

        self.digestSyncService = DigestSyncService(
            settingsRepository: settingsRepository,
            digestRepository: digestRepository
        )

        self.configSyncManager = ConfigSyncManager(
            settingsRepository: settingsRepository
        )

        self.heartbeatService = HeartbeatService(
            settingsRepository: settingsRepository
        )
    }

    // MARK: - Public API

    /// Check if Ghostwriter is configured
    public func isConfigured() async -> Bool {
        do {
            return try await settingsRepository.isGhostwriterConfigured()
        } catch {
            return false
        }
    }

    /// Minimum interval between digest syncs (1 hour)
    private static let digestSyncInterval: TimeInterval = 3600

    /// Perform a full sync with Ghostwriter
    /// Tries the combined /sync endpoint first, falls back to individual calls.
    public func performFullSync() async {
        guard await isConfigured() else {
            logger.debug("Ghostwriter not configured, skipping sync")
            return
        }

        guard !isSyncing else {
            logger.debug("Sync already in progress")
            return
        }

        isSyncing = true
        lastSyncError = nil
        let tracker = SyncPerformanceTracker()

        do {
            logger.info("Starting Ghostwriter sync")

            // 1. Send heartbeat + push feeds concurrently (independent operations)
            await sendHeartbeatAndPushFeeds(tracker: tracker)

            // 3. Try combined sync
            let s = tracker.beginInterval("Combined Sync")
            let combinedSyncSucceeded = await tryCombinedSync(tracker: tracker)
            tracker.endInterval("Combined Sync", state: s)

            if !combinedSyncSucceeded {
                // Fall back to individual calls
                logger.warning("Combined sync failed, falling back to individual calls")

                do {
                    let cs = tracker.beginInterval("Config Sync")
                    _ = try await configSyncManager.sync()
                    tracker.endInterval("Config Sync", state: cs)
                } catch {
                    logger.warning("Config sync failed: \(error.localizedDescription)")
                }

                let fs = tracker.beginInterval("Feed Sync (fallback)")
                try await feedSyncService.sync(tracker: tracker)
                tracker.endInterval("Feed Sync (fallback)", state: fs)

                let shouldSyncDigests = await shouldRunDigestSync()
                if shouldSyncDigests {
                    let ds = tracker.beginInterval("Digest Sync (fallback)")
                    try await digestSyncService.sync(tracker: tracker)
                    tracker.endInterval("Digest Sync (fallback)", state: ds)
                }
            }

            lastSyncTime = Date()
            logger.info("Ghostwriter sync completed successfully")
        } catch {
            logger.error("Ghostwriter sync failed: \(error.localizedDescription)")
            lastSyncError = error
        }

        tracker.logSummary()
        isSyncing = false
    }

    /// Send heartbeat and push feeds concurrently since they're independent operations.
    private func sendHeartbeatAndPushFeeds(tracker: SyncPerformanceTracker) async {
        async let heartbeatResult: Void = {
            do {
                let s = tracker.beginInterval("Heartbeat")
                _ = try await self.heartbeatService.sendHeartbeat()
                tracker.endInterval("Heartbeat", state: s)
            } catch {
                self.logger.warning("Heartbeat failed: \(error.localizedDescription)")
            }
        }()

        async let feedPushResult: Void = {
            do {
                let s = tracker.beginInterval("Feed Push")
                try await self.feedSyncService.pushLocalFeeds(tracker: tracker)
                tracker.endInterval("Feed Push", state: s)
            } catch {
                self.logger.warning("Feed push failed: \(error.localizedDescription)")
            }
        }()

        _ = await (heartbeatResult, feedPushResult)
    }

    /// Try combined sync endpoint. Returns true if successful.
    private func tryCombinedSync(tracker: SyncPerformanceTracker? = nil) async -> Bool {
        do {
            guard let url = try await settingsRepository.getGhostwriterURL() else { return false }
            let apiKey = try await settingsRepository.getGhostwriterAPIKey()
            let client = try GhostwriterClient(baseURLString: url, apiKey: apiKey)

            let feedSince = try await settingsRepository.getLastFeedSyncTime()
            let knownDigestIds = try await digestSyncService.getKnownRemoteIds()

            let s = tracker?.beginInterval("Sync Endpoint Request")
            let syncResponse = try await client.performSync(
                feedSince: feedSince,
                knownDigestIds: knownDigestIds
            )
            if let s { tracker?.endInterval("Sync Endpoint Request", state: s) }

            // Dispatch response to individual handlers
            do {
                try await configSyncManager.applyPreFetchedConfig(syncResponse.config)
            } catch {
                logger.warning("Failed to apply synced config: \(error.localizedDescription)")
            }

            do {
                try await feedSyncService.applyFeedChanges(syncResponse.feeds)
            } catch {
                logger.warning("Failed to apply synced feeds: \(error.localizedDescription)")
            }

            do {
                let ds = tracker?.beginInterval("Process Synced Digests")
                try await digestSyncService.processDigestsFromSync(syncResponse.digests.newDigests, tracker: tracker)
                if let ds { tracker?.endInterval("Process Synced Digests", state: ds) }
            } catch {
                logger.warning("Failed to process synced digests: \(error.localizedDescription)")
            }

            logger.info("Combined sync completed: \(syncResponse.digests.newDigests.count) new digests")
            return true
        } catch {
            logger.warning("Combined sync endpoint failed: \(error.localizedDescription)")
            return false
        }
    }

    /// Force a full sync including digests regardless of timing
    public func performFullSyncIncludingDigests() async {
        guard await isConfigured() else { return }
        guard !isSyncing else { return }

        isSyncing = true
        lastSyncError = nil
        let tracker = SyncPerformanceTracker()

        do {
            logger.info("Starting forced full Ghostwriter sync (including digests)")

            // Send heartbeat + push feeds concurrently (independent operations)
            await sendHeartbeatAndPushFeeds(tracker: tracker)

            // Try combined sync
            let s = tracker.beginInterval("Combined Sync")
            let combinedSyncSucceeded = await tryCombinedSync(tracker: tracker)
            tracker.endInterval("Combined Sync", state: s)

            if !combinedSyncSucceeded {
                do {
                    let cs = tracker.beginInterval("Config Sync")
                    _ = try await configSyncManager.sync()
                    tracker.endInterval("Config Sync", state: cs)
                } catch {}
                let fs = tracker.beginInterval("Feed Sync (fallback)")
                try await feedSyncService.sync(tracker: tracker)
                tracker.endInterval("Feed Sync (fallback)", state: fs)
                let ds = tracker.beginInterval("Digest Sync (fallback)")
                try await digestSyncService.sync(tracker: tracker)
                tracker.endInterval("Digest Sync (fallback)", state: ds)
            }

            lastSyncTime = Date()
            logger.info("Forced full sync completed")
        } catch {
            logger.error("Forced full sync failed: \(error.localizedDescription)")
            lastSyncError = error
        }

        tracker.logSummary()
        isSyncing = false
    }

    /// Check if enough time has passed since the last digest sync
    private func shouldRunDigestSync() async -> Bool {
        do {
            guard let lastDigestSync = try await settingsRepository.getLastDigestSyncTime() else {
                return true // Never synced
            }
            let elapsed = Date().timeIntervalSince(lastDigestSync)
            return elapsed >= Self.digestSyncInterval
        } catch {
            return true // On error, sync to be safe
        }
    }

    /// Sync only feeds
    public func syncFeeds() async throws {
        try await feedSyncService.sync()
    }

    /// Sync only digests
    public func syncDigests() async throws {
        try await digestSyncService.sync()
    }

    /// Trigger a digest generation on the server
    public func triggerDigest(period: String = "manual") async throws -> DigestTriggerResponse {
        return try await digestSyncService.triggerDigest(period: period)
    }

    /// Get the status of a running digest job
    public func getDigestStatus(digestId: String) async throws -> DigestStatusResponse {
        return try await digestSyncService.getDigestStatus(digestId: digestId)
    }

    /// Notify server when a feed is deleted locally
    public func notifyFeedDeleted(url: String) async throws {
        try await feedSyncService.notifyFeedDeleted(url: url)
    }

    /// Check server health
    public func checkServerHealth() async throws -> HealthResponse {
        return try await heartbeatService.checkHealth()
    }

    /// Get client status from server
    public func getClientStatus() async throws -> ClientStatusResponse {
        return try await heartbeatService.getClientStatus()
    }
}
