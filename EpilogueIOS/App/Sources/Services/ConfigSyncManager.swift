//
//  ConfigSyncManager.swift
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

/// Manages configuration sync between the app and Ghostwriter backend
///
/// Sync strategy: Last-write-wins based on timestamps
/// - If server config is newer → apply server config locally
/// - If local config is newer → push local config to server
/// - On conflict (409) → re-fetch server config (server wins)
@MainActor
public final class ConfigSyncManager {
    private let settingsRepository: SettingsRepositoryProtocol
    private let sharedSyncBridge: SharedConfigSyncBridge
    private let logger = Logger(subsystem: "com.epilogue", category: "ConfigSync")

    public init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
        self.sharedSyncBridge = makeSharedConfigSyncBridge(settingsRepository: settingsRepository)
    }

    /// Sync configuration with server (call on app launch)
    /// - Returns: true if sync was successful
    @discardableResult
    public func sync() async throws -> Bool {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            logger.debug("Ghostwriter not configured, skipping config sync")
            return false
        }

        logger.info("Starting config sync with Ghostwriter")
        let success = try await sharedSyncBridge.syncConfig()
        if !success {
            throw GhostwriterError.httpError(statusCode: 500, message: "Config sync failed")
        }
        return success
    }

    /// Apply a pre-fetched config from the combined sync endpoint.
    /// Uses the same last-write-wins logic as regular sync.
    public func applyPreFetchedConfig(_ config: ClientConfigResponse) async throws {
        let success = try await sharedSyncBridge.applyPreFetchedConfig(config)
        if !success {
            throw GhostwriterError.httpError(statusCode: 500, message: "Failed applying pre-fetched config")
        }
    }

    /// Push a schedule enable/disable change to server immediately.
    public func updateSchedule(period: DigestPeriod, enabled: Bool) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            return
        }

        let client = try await createClient()
        _ = try await client.updateSchedule(
            period: period.serverPeriod,
            request: ScheduleUpdateRequest(enabled: enabled)
        )
        logger.info("Updated schedule \(period.serverPeriod), enabled=\(enabled)")
    }

    /// Push min_word_count to server immediately.
    public func pushMinWordCount(_ count: Int) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            return
        }

        let success = try await sharedSyncBridge.pushMinWordCount(count)
        if success {
            logger.info("Pushed min_word_count to server: \(count)")
        } else {
            logger.warning("Shared min_word_count push failed; keeping local value for retry")
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

    // Shared config sync use-case now owns timestamp comparison and conflict handling.
}
