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

        let client = try await createClient()
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()
        let request = ClientConfigUpdateRequest(
            minWordCount: count,
            clientUpdatedAt: localTimestamp
        )

        do {
            let response = try await client.updateConfig(request)
            try await settingsRepository.setGhostwriterConfigUpdatedAt(response.updatedAt)
            logger.info("Pushed min_word_count to server: \(count)")
        } catch GhostwriterError.conflict {
            // Server was modified, re-sync
            logger.warning("Conflict pushing min_word_count, re-syncing")
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
        // Prefer v2 hour/minute fields, fallback to legacy HH:mm strings.
        let morning = Self.resolveTime(
            hour: config.morningHour,
            minute: config.morningMinute,
            legacyTime: config.scheduleMorning,
            defaultHour: 7,
            defaultMinute: 0
        )
        let noon = Self.resolveTime(
            hour: config.noonHour,
            minute: config.noonMinute,
            legacyTime: config.scheduleNoon,
            defaultHour: 12,
            defaultMinute: 0
        )
        let evening = Self.resolveTime(
            hour: config.eveningHour,
            minute: config.eveningMinute,
            legacyTime: config.scheduleEvening,
            defaultHour: 18,
            defaultMinute: 0
        )

        // Apply schedule times (for display - server handles actual scheduling)
        try await settingsRepository.setGhostwriterSchedule(
            morningHour: morning.hour,
            morningMinute: morning.minute,
            noonHour: noon.hour,
            noonMinute: noon.minute,
            eveningHour: evening.hour,
            eveningMinute: evening.minute,
            timezone: config.timezone
        )

        if let minWordCount = config.minWordCount {
            try await settingsRepository.setMinWordCount(minWordCount)
        }

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

    private static func resolveTime(
        hour: Int?,
        minute: Int?,
        legacyTime: String?,
        defaultHour: Int,
        defaultMinute: Int
    ) -> (hour: Int, minute: Int) {
        if let hour, let minute {
            return (hour, minute)
        }
        return parseTime(legacyTime) ?? (defaultHour, defaultMinute)
    }

    private func pushLocalConfig(client: GhostwriterClient) async throws {
        let localTimestamp = try await settingsRepository.getGhostwriterConfigUpdatedAt()
        let schedule = try await settingsRepository.getGhostwriterSchedule()
        let minWordCount = try await settingsRepository.getMinWordCount()

        let request = ClientConfigUpdateRequest(
            minWordCount: minWordCount,
            morningHour: schedule?.morningHour,
            morningMinute: schedule?.morningMinute,
            noonHour: schedule?.noonHour,
            noonMinute: schedule?.noonMinute,
            eveningHour: schedule?.eveningHour,
            eveningMinute: schedule?.eveningMinute,
            timezone: schedule?.timezone,
            // Legacy payload for older server builds.
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
