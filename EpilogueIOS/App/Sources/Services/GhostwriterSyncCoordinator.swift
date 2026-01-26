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

    /// Perform a full sync with Ghostwriter
    /// This syncs config, feeds, and digests
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

        do {
            logger.info("Starting full Ghostwriter sync")

            // 1. Send heartbeat
            do {
                _ = try await heartbeatService.sendHeartbeat()
            } catch {
                logger.warning("Heartbeat failed: \(error.localizedDescription)")
                // Continue with sync even if heartbeat fails
            }

            // 2. Sync config
            do {
                _ = try await configSyncManager.sync()
            } catch {
                logger.warning("Config sync failed: \(error.localizedDescription)")
                // Continue with other syncs
            }

            // 3. Sync feeds
            try await feedSyncService.sync()

            // 4. Sync digests
            try await digestSyncService.sync()

            lastSyncTime = Date()
            logger.info("Full Ghostwriter sync completed successfully")
        } catch {
            logger.error("Ghostwriter sync failed: \(error.localizedDescription)")
            lastSyncError = error
        }

        isSyncing = false
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
