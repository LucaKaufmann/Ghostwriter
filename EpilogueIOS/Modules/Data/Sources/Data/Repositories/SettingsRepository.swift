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
    }

    // UserDefaults keys
    private enum DefaultsKeys {
        static let scheduledHour = "scheduled_hour"
        static let scheduleEnabled = "schedule_enabled"
        static let minWordCount = "min_word_count"
        static let aiProvider = "ai_provider"
        static let aiModel = "ai_model"
        static let showNotifications = "show_notifications"
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

    public func getScheduledHour() async throws -> Int {
        let hour = userDefaults.integer(forKey: DefaultsKeys.scheduledHour)
        // If not set (0), return default
        return hour == 0 ? Defaults.scheduledHour : hour
    }

    public func setScheduledHour(_ hour: Int) async throws {
        guard hour >= 0 && hour <= 23 else {
            throw SettingsRepositoryError.invalidHour
        }
        userDefaults.set(hour, forKey: DefaultsKeys.scheduledHour)
    }

    public func isScheduleEnabled() async throws -> Bool {
        // Check if key exists
        if userDefaults.object(forKey: DefaultsKeys.scheduleEnabled) == nil {
            return Defaults.scheduleEnabled
        }
        return userDefaults.bool(forKey: DefaultsKeys.scheduleEnabled)
    }

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
