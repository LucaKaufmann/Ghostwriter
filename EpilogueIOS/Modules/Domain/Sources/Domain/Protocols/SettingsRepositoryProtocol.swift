//
//  SettingsRepositoryProtocol.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Protocol defining settings and configuration operations.
/// Uses Keychain for sensitive data (API keys) and UserDefaults for preferences.
public protocol SettingsRepositoryProtocol: Sendable {
    // MARK: - API Key Management

    /// Gets the stored OpenAI API key from Keychain
    func getOpenAIKey() async throws -> String?

    /// Stores the OpenAI API key in Keychain
    func setOpenAIKey(_ key: String) async throws

    /// Deletes the OpenAI API key from Keychain
    func deleteOpenAIKey() async throws

    // MARK: - Schedule Settings

    /// Gets the scheduled digest generation time (hour in 24-hour format)
    func getScheduledHour() async throws -> Int

    /// Sets the scheduled digest generation time (hour in 24-hour format, 0-23)
    func setScheduledHour(_ hour: Int) async throws

    /// Gets whether scheduled digest generation is enabled
    func isScheduleEnabled() async throws -> Bool

    /// Sets whether scheduled digest generation is enabled
    func setScheduleEnabled(_ enabled: Bool) async throws

    // MARK: - Content Filters

    /// Gets the minimum word count for FIDELITY mode articles
    /// Articles below this count are filtered out. 0 = no filter.
    func getMinWordCount() async throws -> Int

    /// Sets the minimum word count for FIDELITY mode articles
    func setMinWordCount(_ count: Int) async throws

    // MARK: - AI Service Settings

    /// Gets the preferred AI service provider
    func getAIProvider() async throws -> AIProvider

    /// Sets the preferred AI service provider
    func setAIProvider(_ provider: AIProvider) async throws

    /// Gets the AI model to use (e.g., "gpt-4o-mini")
    func getAIModel() async throws -> String

    /// Sets the AI model to use
    func setAIModel(_ model: String) async throws

    // MARK: - App Preferences

    /// Gets whether to show EPUB generation notifications
    func shouldShowNotifications() async throws -> Bool

    /// Sets whether to show EPUB generation notifications
    func setShouldShowNotifications(_ enabled: Bool) async throws

    // MARK: - Ghostwriter Settings

    /// Gets whether Ghostwriter sync is enabled
    func isGhostwriterEnabled() async throws -> Bool

    /// Sets whether Ghostwriter sync is enabled
    func setGhostwriterEnabled(_ enabled: Bool) async throws

    /// Gets the Ghostwriter server URL
    func getGhostwriterURL() async throws -> String?

    /// Sets the Ghostwriter server URL
    func setGhostwriterURL(_ url: String?) async throws

    /// Gets the Ghostwriter API key from Keychain
    func getGhostwriterAPIKey() async throws -> String?

    /// Stores the Ghostwriter API key in Keychain
    func setGhostwriterAPIKey(_ key: String?) async throws

    /// Gets the timestamp of the last feed sync with Ghostwriter
    func getLastFeedSyncTime() async throws -> Date?

    /// Sets the timestamp of the last feed sync with Ghostwriter
    func setLastFeedSyncTime(_ date: Date?) async throws

    /// Gets the timestamp of the last digest sync with Ghostwriter
    func getLastDigestSyncTime() async throws -> Date?

    /// Sets the timestamp of the last digest sync with Ghostwriter
    func setLastDigestSyncTime(_ date: Date?) async throws

    /// Gets the server's config updated_at timestamp (for conflict detection)
    func getGhostwriterConfigUpdatedAt() async throws -> String?

    /// Sets the server's config updated_at timestamp
    func setGhostwriterConfigUpdatedAt(_ timestamp: String?) async throws

    /// Checks if Ghostwriter is configured (enabled + has URL)
    func isGhostwriterConfigured() async throws -> Bool
}

/// Available AI service providers
public enum AIProvider: String, Codable, CaseIterable, Sendable {
    case openAI = "openai"
    case anthropic = "anthropic"
    case appleIntelligence = "apple"

    public var displayName: String {
        switch self {
        case .openAI:
            return "OpenAI"
        case .anthropic:
            return "Anthropic"
        case .appleIntelligence:
            return "Apple Intelligence"
        }
    }
}
