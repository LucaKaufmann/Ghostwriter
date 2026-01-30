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

    /// Apply a pre-fetched config from the combined sync endpoint.
    /// Uses the same last-write-wins logic as regular sync.
    public func applyPreFetchedConfig(_ config: ClientConfigResponse) async throws {
        let localUpdatedAt = try await settingsRepository.getGhostwriterConfigUpdatedAt()

        if localUpdatedAt == nil {
            try await applyServerConfig(config)
            return
        }

        guard let serverTime = config.parsedUpdatedAt(),
              let localTime = localUpdatedAt?.toISO8601Date() else {
            try await applyServerConfig(config)
            return
        }

        if serverTime >= localTime {
            try await applyServerConfig(config)
        }
        // If local is newer, don't overwrite — regular sync will push later
    }

    /// Push a specific setting change to server immediately
    public func pushSchedule(morning: String, noon: String, evening: String, timezone: String) async throws {
        guard try await settingsRepository.isGhostwriterConfigured() else {
            return
        }

        let client = try await createClient()
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()

        let request = ClientConfigUpdateRequest(
            timezone: timezone,
            scheduleMorning: morning,
            scheduleNoon: noon,
            scheduleEvening: evening,
            clientUpdatedAt: localTimestamp
        )

        do {
            let response = try await client.updateConfig(request)
            try await settingsRepository.setGhostwriterConfigUpdatedAt(response.updatedAt)
            logger.info("Pushed schedule to server")
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
        // Parse schedule times from "HH:mm" strings into hour/minute
        let morning = Self.parseTime(config.scheduleMorning)
        let noon = Self.parseTime(config.scheduleNoon)
        let evening = Self.parseTime(config.scheduleEvening)

        // Apply schedule times (for display - server handles actual scheduling)
        try await settingsRepository.setGhostwriterSchedule(
            morningHour: morning?.hour ?? 7,
            morningMinute: morning?.minute ?? 0,
            noonHour: noon?.hour ?? 12,
            noonMinute: noon?.minute ?? 0,
            eveningHour: evening?.hour ?? 18,
            eveningMinute: evening?.minute ?? 0,
            timezone: config.timezone
        )

        // Save server's updated_at timestamp for future comparisons
        try await settingsRepository.setGhostwriterConfigUpdatedAt(config.updatedAt)

        logger.info("Applied server config: schedule times synced, timezone=\(config.timezone)")
    }

    /// Parse "HH:mm" time string into hour and minute components
    private static func parseTime(_ timeString: String?) -> (hour: Int, minute: Int)? {
        guard let timeString else { return nil }
        let parts = timeString.split(separator: ":")
        guard parts.count == 2,
              let hour = Int(parts[0]),
              let minute = Int(parts[1]) else { return nil }
        return (hour, minute)
    }

    private func pushLocalConfig(client: GhostwriterClient) async throws {
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()
        let schedule = try await settingsRepository.getGhostwriterSchedule()

        let request = ClientConfigUpdateRequest(
            timezone: schedule?.timezone,
            scheduleMorning: schedule.map { String(format: "%02d:%02d", $0.morningHour, $0.morningMinute) },
            scheduleNoon: schedule.map { String(format: "%02d:%02d", $0.noonHour, $0.noonMinute) },
            scheduleEvening: schedule.map { String(format: "%02d:%02d", $0.eveningHour, $0.eveningMinute) },
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
