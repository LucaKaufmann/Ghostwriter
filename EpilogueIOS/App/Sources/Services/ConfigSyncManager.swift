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
    private let logger = Logger(subsystem: "com.epilogue", category: "ConfigSync")

    public init(settingsRepository: SettingsRepositoryProtocol) {
        self.settingsRepository = settingsRepository
    }

    /// Sync configuration with server (call on app launch)
    /// - Returns: true if sync was successful
    @discardableResult
    public func sync() async throws -> Bool {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            logger.debug("Ghostwriter not configured, skipping config sync")
            return false
        }

        let client = try await createClient()

        logger.info("Starting config sync with Ghostwriter")

        // Get server config
        let serverConfig = try await client.getConfig()
        let localUpdatedAt = try await settingsRepository.getGhostwriterConfigUpdatedAt()

        if localUpdatedAt == nil {
            // First sync - apply server config
            logger.info("First sync, applying server config")
            try await applyServerConfig(serverConfig)
            return true
        }

        // Compare timestamps
        guard let serverTime = serverConfig.parsedUpdatedAt(),
              let localTime = localUpdatedAt?.toISO8601Date() else {
            // Can't compare, default to applying server config
            logger.warning("Could not parse timestamps, applying server config")
            try await applyServerConfig(serverConfig)
            return true
        }

        if serverTime > localTime {
            // Server is newer - apply server config
            logger.info("Server config is newer, applying")
            try await applyServerConfig(serverConfig)
        } else if localTime > serverTime {
            // Local is newer - push to server
            logger.info("Local config is newer, pushing to server")
            try await pushLocalConfig(client: client)
        } else {
            logger.info("Config is in sync")
        }

        return true
    }

    /// Push a specific setting change to server immediately
    public func pushMinWordCount(_ count: Int) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            return
        }

        let client = try await createClient()
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()

        let request = ClientConfigUpdateRequest(
            minWordCount: count,
            clientUpdatedAt: localTimestamp
        )

        do {
            let response = try await client.updateConfig(request)
            try await settingsRepository.setGhostwriterConfigUpdatedAt(response.updatedAt)
            logger.info("Pushed min word count to server: \(count)")
        } catch GhostwriterError.conflict {
            // Server was modified, re-sync
            logger.warning("Conflict pushing config, re-syncing")
            try await sync()
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

    private func applyServerConfig(_ config: ClientConfigResponse) async throws {
        // Apply min word count
        try await settingsRepository.setMinWordCount(config.minWordCount)

        // Apply schedule times (for display - server handles actual scheduling)
        try await settingsRepository.setGhostwriterSchedule(
            morningHour: config.morningHour,
            morningMinute: config.morningMinute,
            noonHour: config.noonHour,
            noonMinute: config.noonMinute,
            eveningHour: config.eveningHour,
            eveningMinute: config.eveningMinute,
            timezone: config.timezone
        )

        // Save server's updated_at timestamp for future comparisons
        try await settingsRepository.setGhostwriterConfigUpdatedAt(config.updatedAt)

        logger.info("Applied server config: minWordCount=\(config.minWordCount), schedule times synced")
    }

    private func pushLocalConfig(client: GhostwriterClient) async throws {
        let minWordCount = try await settingsRepository.getMinWordCount()
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()

        let request = ClientConfigUpdateRequest(
            minWordCount: minWordCount,
            clientUpdatedAt: localTimestamp
        )

        do {
            let response = try await client.updateConfig(request)
            try await settingsRepository.setGhostwriterConfigUpdatedAt(response.updatedAt)
            logger.info("Pushed local config to server")
        } catch GhostwriterError.conflict {
            // Conflict - server wins, re-fetch and apply
            logger.warning("Conflict detected, re-fetching server config")
            let serverConfig = try await client.getConfig()
            try await applyServerConfig(serverConfig)
        }
    }
}
