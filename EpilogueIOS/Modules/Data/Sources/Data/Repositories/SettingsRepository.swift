//
//  SettingsRepository.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain

/// Implementation of SettingsRepositoryProtocol using UserDefaults and Keychain
public final class SettingsRepository: SettingsRepositoryProtocol {
    private let userDefaults: UserDefaults
    private let keychainService: KeychainService

    // Keychain keys
    private enum KeychainKeys {
        static let openAIKey = "openai_api_key"
        static let ghostwriterAPIKey = "ghostwriter_api_key"
    }

    // UserDefaults keys
    private enum DefaultsKeys {
        static let scheduledHour = "scheduled_hour" // Deprecated
        static let scheduleEnabled = "schedule_enabled" // Deprecated
        static let enabledPeriods = "enabled_periods" // New: Set<String>
        static let minWordCount = "min_word_count"
        static let aiProvider = "ai_provider"
        static let aiModel = "ai_model"
        static let showNotifications = "show_notifications"
        static let einkMode = "eink_mode"
        static let customExportEnabled = "custom_export_enabled"
        static let customExportBookmark = "custom_export_bookmark"
        // Ghostwriter settings
        static let ghostwriterEnabled = "ghostwriter_enabled"
        static let ghostwriterURL = "ghostwriter_url"
        static let lastFeedSyncTime = "ghostwriter_last_feed_sync"
        static let lastDigestSyncTime = "ghostwriter_last_digest_sync"
        static let ghostwriterConfigUpdatedAt = "ghostwriter_config_updated_at"
        // Ghostwriter schedule (synced from server)
        static let ghostwriterMorningHour = "ghostwriter_morning_hour"
        static let ghostwriterMorningMinute = "ghostwriter_morning_minute"
        static let ghostwriterNoonHour = "ghostwriter_noon_hour"
        static let ghostwriterNoonMinute = "ghostwriter_noon_minute"
        static let ghostwriterEveningHour = "ghostwriter_evening_hour"
        static let ghostwriterEveningMinute = "ghostwriter_evening_minute"
        static let ghostwriterTimezone = "ghostwriter_timezone"
    }

    // Default values
    private enum Defaults {
        static let scheduledHour = 6 // 6 AM
        static let scheduleEnabled = true
        static let minWordCount = 300
        static let aiProvider = AIProvider.openAI
        static let aiModel = "gpt-4o-mini"
        static let showNotifications = true
    }

    public init(
        userDefaults: UserDefaults = .standard,
        keychainService: KeychainService = KeychainService()
    ) {
        self.userDefaults = userDefaults
        self.keychainService = keychainService
    }

    // MARK: - API Key Management

    public func getOpenAIKey() async throws -> String? {
        try keychainService.retrieve(forKey: KeychainKeys.openAIKey)
    }

    public func setOpenAIKey(_ key: String) async throws {
        try keychainService.save(key, forKey: KeychainKeys.openAIKey)
    }

    public func deleteOpenAIKey() async throws {
        try keychainService.delete(forKey: KeychainKeys.openAIKey)
    }

    // MARK: - Schedule Settings

    public func getEnabledPeriods() async throws -> Set<DigestPeriod> {
        guard let rawValues = userDefaults.stringArray(forKey: DefaultsKeys.enabledPeriods) else {
            // Default: morning enabled
            return [.morning]
        }
        return Set(rawValues.compactMap { DigestPeriod(rawValue: $0) })
    }

    public func setEnabledPeriods(_ periods: Set<DigestPeriod>) async throws {
        let rawValues = periods.map { $0.rawValue }
        userDefaults.set(rawValues, forKey: DefaultsKeys.enabledPeriods)
    }

    public func togglePeriod(_ period: DigestPeriod, enabled: Bool) async throws {
        var periods = try await getEnabledPeriods()
        if enabled {
            periods.insert(period)
        } else {
            periods.remove(period)
        }
        try await setEnabledPeriods(periods)
    }

    public func isPeriodEnabled(_ period: DigestPeriod) async throws -> Bool {
        let periods = try await getEnabledPeriods()
        return periods.contains(period)
    }

    public func isScheduleEnabled() async throws -> Bool {
        let periods = try await getEnabledPeriods()
        return !periods.isEmpty
    }

    // Legacy support - deprecated
    @available(*, deprecated, message: "Use getEnabledPeriods instead")
    public func getScheduledHour() async throws -> Int {
        let hour = userDefaults.integer(forKey: DefaultsKeys.scheduledHour)
        return hour == 0 ? Defaults.scheduledHour : hour
    }

    @available(*, deprecated, message: "Use setEnabledPeriods instead")
    public func setScheduledHour(_ hour: Int) async throws {
        guard hour >= 0 && hour <= 23 else {
            throw SettingsRepositoryError.invalidHour
        }
        userDefaults.set(hour, forKey: DefaultsKeys.scheduledHour)
    }

    @available(*, deprecated, message: "Use setEnabledPeriods instead")
    public func setScheduleEnabled(_ enabled: Bool) async throws {
        userDefaults.set(enabled, forKey: DefaultsKeys.scheduleEnabled)
    }

    // MARK: - Content Filters

    public func getMinWordCount() async throws -> Int {
        let count = userDefaults.integer(forKey: DefaultsKeys.minWordCount)
        return count == 0 ? Defaults.minWordCount : count
    }

    public func setMinWordCount(_ count: Int) async throws {
        guard count >= 0 else {
            throw SettingsRepositoryError.invalidWordCount
        }
        userDefaults.set(count, forKey: DefaultsKeys.minWordCount)
    }

    // MARK: - AI Service Settings

    public func getAIProvider() async throws -> AIProvider {
        guard let rawValue = userDefaults.string(forKey: DefaultsKeys.aiProvider),
              let provider = AIProvider(rawValue: rawValue) else {
            return Defaults.aiProvider
        }
        return provider
    }

    public func setAIProvider(_ provider: AIProvider) async throws {
        userDefaults.set(provider.rawValue, forKey: DefaultsKeys.aiProvider)
    }

    public func getAIModel() async throws -> String {
        guard let model = userDefaults.string(forKey: DefaultsKeys.aiModel) else {
            return Defaults.aiModel
        }
        return model
    }

    public func setAIModel(_ model: String) async throws {
        guard !model.isEmpty else {
            throw SettingsRepositoryError.invalidModel
        }
        userDefaults.set(model, forKey: DefaultsKeys.aiModel)
    }

    // MARK: - App Preferences

    public func shouldShowNotifications() async throws -> Bool {
        if userDefaults.object(forKey: DefaultsKeys.showNotifications) == nil {
            return Defaults.showNotifications
        }
        return userDefaults.bool(forKey: DefaultsKeys.showNotifications)
    }

    public func setShouldShowNotifications(_ enabled: Bool) async throws {
        userDefaults.set(enabled, forKey: DefaultsKeys.showNotifications)
    }

    // MARK: - Display Settings

    public func isEinkModeEnabled() async throws -> Bool {
        userDefaults.bool(forKey: DefaultsKeys.einkMode)
    }

    public func setEinkModeEnabled(_ enabled: Bool) async throws {
        userDefaults.set(enabled, forKey: DefaultsKeys.einkMode)
    }

    // MARK: - Export Settings

    public func getCustomExportEnabled() async throws -> Bool {
        return userDefaults.bool(forKey: DefaultsKeys.customExportEnabled)
    }

    public func setCustomExportEnabled(_ enabled: Bool) async throws {
        userDefaults.set(enabled, forKey: DefaultsKeys.customExportEnabled)
    }

    public func getCustomExportBookmark() async throws -> Data? {
        return userDefaults.data(forKey: DefaultsKeys.customExportBookmark)
    }

    public func setCustomExportBookmark(_ bookmark: Data?) async throws {
        if let bookmark {
            userDefaults.set(bookmark, forKey: DefaultsKeys.customExportBookmark)
        } else {
            userDefaults.removeObject(forKey: DefaultsKeys.customExportBookmark)
        }
    }

    // MARK: - Ghostwriter Settings

    public func isGhostwriterEnabled() async throws -> Bool {
        return userDefaults.bool(forKey: DefaultsKeys.ghostwriterEnabled)
    }

    public func setGhostwriterEnabled(_ enabled: Bool) async throws {
        userDefaults.set(enabled, forKey: DefaultsKeys.ghostwriterEnabled)
    }

    public func getGhostwriterURL() async throws -> String? {
        return userDefaults.string(forKey: DefaultsKeys.ghostwriterURL)
    }

    public func setGhostwriterURL(_ url: String?) async throws {
        if let url = url {
            userDefaults.set(url, forKey: DefaultsKeys.ghostwriterURL)
        } else {
            userDefaults.removeObject(forKey: DefaultsKeys.ghostwriterURL)
        }
    }

    public func getGhostwriterAPIKey() async throws -> String? {
        return try keychainService.retrieve(forKey: KeychainKeys.ghostwriterAPIKey)
    }

    public func setGhostwriterAPIKey(_ key: String?) async throws {
        if let key = key, !key.isEmpty {
            try keychainService.save(key, forKey: KeychainKeys.ghostwriterAPIKey)
        } else {
            try keychainService.delete(forKey: KeychainKeys.ghostwriterAPIKey)
        }
    }

    public func getLastFeedSyncTime() async throws -> Date? {
        let timestamp = userDefaults.double(forKey: DefaultsKeys.lastFeedSyncTime)
        return timestamp > 0 ? Date(timeIntervalSince1970: timestamp) : nil
    }

    public func setLastFeedSyncTime(_ date: Date?) async throws {
        if let date = date {
            userDefaults.set(date.timeIntervalSince1970, forKey: DefaultsKeys.lastFeedSyncTime)
        } else {
            userDefaults.removeObject(forKey: DefaultsKeys.lastFeedSyncTime)
        }
    }

    public func getLastDigestSyncTime() async throws -> Date? {
        let timestamp = userDefaults.double(forKey: DefaultsKeys.lastDigestSyncTime)
        return timestamp > 0 ? Date(timeIntervalSince1970: timestamp) : nil
    }

    public func setLastDigestSyncTime(_ date: Date?) async throws {
        if let date = date {
            userDefaults.set(date.timeIntervalSince1970, forKey: DefaultsKeys.lastDigestSyncTime)
        } else {
            userDefaults.removeObject(forKey: DefaultsKeys.lastDigestSyncTime)
        }
    }

    public func getGhostwriterConfigUpdatedAt() async throws -> String? {
        return userDefaults.string(forKey: DefaultsKeys.ghostwriterConfigUpdatedAt)
    }

    public func setGhostwriterConfigUpdatedAt(_ timestamp: String?) async throws {
        if let timestamp = timestamp {
            userDefaults.set(timestamp, forKey: DefaultsKeys.ghostwriterConfigUpdatedAt)
        } else {
            userDefaults.removeObject(forKey: DefaultsKeys.ghostwriterConfigUpdatedAt)
        }
    }

    public func isGhostwriterConfigured() async throws -> Bool {
        let enabled = try await isGhostwriterEnabled()
        let url = try await getGhostwriterURL()
        return enabled && url != nil && !url!.isEmpty
    }

    public func setGhostwriterSchedule(
        morningHour: Int,
        morningMinute: Int,
        noonHour: Int,
        noonMinute: Int,
        eveningHour: Int,
        eveningMinute: Int,
        timezone: String
    ) async throws {
        userDefaults.set(morningHour, forKey: DefaultsKeys.ghostwriterMorningHour)
        userDefaults.set(morningMinute, forKey: DefaultsKeys.ghostwriterMorningMinute)
        userDefaults.set(noonHour, forKey: DefaultsKeys.ghostwriterNoonHour)
        userDefaults.set(noonMinute, forKey: DefaultsKeys.ghostwriterNoonMinute)
        userDefaults.set(eveningHour, forKey: DefaultsKeys.ghostwriterEveningHour)
        userDefaults.set(eveningMinute, forKey: DefaultsKeys.ghostwriterEveningMinute)
        userDefaults.set(timezone, forKey: DefaultsKeys.ghostwriterTimezone)
    }

    public func getGhostwriterSchedule() async throws -> GhostwriterSchedule? {
        // Check if we have schedule data (timezone is required)
        guard let timezone = userDefaults.string(forKey: DefaultsKeys.ghostwriterTimezone) else {
            return nil
        }

        return GhostwriterSchedule(
            morningHour: userDefaults.integer(forKey: DefaultsKeys.ghostwriterMorningHour),
            morningMinute: userDefaults.integer(forKey: DefaultsKeys.ghostwriterMorningMinute),
            noonHour: userDefaults.integer(forKey: DefaultsKeys.ghostwriterNoonHour),
            noonMinute: userDefaults.integer(forKey: DefaultsKeys.ghostwriterNoonMinute),
            eveningHour: userDefaults.integer(forKey: DefaultsKeys.ghostwriterEveningHour),
            eveningMinute: userDefaults.integer(forKey: DefaultsKeys.ghostwriterEveningMinute),
            timezone: timezone
        )
    }
}

// MARK: - Errors

public enum SettingsRepositoryError: LocalizedError {
    case invalidHour
    case invalidWordCount
    case invalidModel

    public var errorDescription: String? {
        switch self {
        case .invalidHour:
            return "Hour must be between 0 and 23"
        case .invalidWordCount:
            return "Word count must be non-negative"
        case .invalidModel:
            return "Model name cannot be empty"
        }
    }
}
