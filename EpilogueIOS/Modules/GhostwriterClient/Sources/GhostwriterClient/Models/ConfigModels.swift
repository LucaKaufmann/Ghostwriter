//
//  ConfigModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Response Models

/// Status of an external integration (Wallabag, Newsletters, etc.)
public struct IntegrationStatus: Codable, Sendable {
    public let enabled: Bool
    public let label: String?

    public init(enabled: Bool, label: String? = nil) {
        self.enabled = enabled
        self.label = label
    }
}

/// Preview article for integration previews.
public struct PreviewArticleResponse: Codable, Sendable {
    public let title: String
    public let url: String
    public let author: String?
    public let wordCount: Int?

    enum CodingKeys: String, CodingKey {
        case title
        case url
        case author
        case wordCount = "word_count"
    }
}

/// Generic preview response for Wallabag/Newsletters.
public struct PreviewResponse: Codable, Sendable {
    public let status: String
    public let count: Int?
    public let articles: [PreviewArticleResponse]?
    public let detail: String?
}

/// Response for clear-seen endpoints.
public struct ClearSeenResponse: Codable, Sendable {
    public let cleared: Int
}

/// Response model for client configuration (shared settings)
public struct ClientConfigResponse: Codable, Sendable {
    public let minWordCount: Int?
    public let morningHour: Int?
    public let morningMinute: Int?
    public let noonHour: Int?
    public let noonMinute: Int?
    public let eveningHour: Int?
    public let eveningMinute: Int?
    public let timezone: String
    public let aiProvider: String?
    public let aiModel: String?
    public let scheduleMorning: String?
    public let scheduleNoon: String?
    public let scheduleEvening: String?
    public let whisperProvider: String?
    public let whisperModel: String?
    public let whisperTimeoutMinutes: Int?
    public let mediaProcessingIntervalHours: Int?
    public let includePodcastsInDigest: Bool?
    public let includeYoutubeInDigest: Bool?
    public let coverEnabled: Bool?
    public let coverProvider: String?
    public let coverQuality: String?
    public let coverPrompt: String?
    public let coverOverlayEnabled: Bool?
    public let coverOpenAIAPIKey: String?
    public let coverGeminiAPIKey: String?
    public let updatedAt: String?
    // Integration status
    public let wallabag: IntegrationStatus?
    public let newsletters: IntegrationStatus?

    enum CodingKeys: String, CodingKey {
        case minWordCount = "min_word_count"
        case morningHour = "morning_hour"
        case morningMinute = "morning_minute"
        case noonHour = "noon_hour"
        case noonMinute = "noon_minute"
        case eveningHour = "evening_hour"
        case eveningMinute = "evening_minute"
        case timezone
        case aiProvider = "ai_provider"
        case aiModel = "ai_model"
        case scheduleMorning = "schedule_morning"
        case scheduleNoon = "schedule_noon"
        case scheduleEvening = "schedule_evening"
        case whisperProvider = "whisper_provider"
        case whisperModel = "whisper_model"
        case whisperTimeoutMinutes = "whisper_timeout_minutes"
        case mediaProcessingIntervalHours = "media_processing_interval_hours"
        case includePodcastsInDigest = "include_podcasts_in_digest"
        case includeYoutubeInDigest = "include_youtube_in_digest"
        case coverEnabled = "cover_enabled"
        case coverProvider = "cover_provider"
        case coverQuality = "cover_quality"
        case coverPrompt = "cover_prompt"
        case coverOverlayEnabled = "cover_overlay_enabled"
        case coverOpenAIAPIKey = "cover_openai_api_key"
        case coverGeminiAPIKey = "cover_gemini_api_key"
        case updatedAt = "updated_at"
        case wallabag
        case newsletters
    }

    /// Parse the updatedAt timestamp to a Date
    public func parsedUpdatedAt() -> Date? {
        guard let updatedAt else { return nil }
        return ISO8601DateFormatter.flexibleFormatter.date(from: updatedAt)
    }
}

// MARK: - Request Models

/// Request model for updating client configuration
public struct ClientConfigUpdateRequest: Codable, Sendable {
    public let minWordCount: Int?
    public let morningHour: Int?
    public let morningMinute: Int?
    public let noonHour: Int?
    public let noonMinute: Int?
    public let eveningHour: Int?
    public let eveningMinute: Int?
    public let timezone: String?
    /// Legacy compatibility fields for older server versions.
    public let scheduleMorning: String?
    public let scheduleNoon: String?
    public let scheduleEvening: String?
    public let clientUpdatedAt: String?

    public init(
        minWordCount: Int? = nil,
        morningHour: Int? = nil,
        morningMinute: Int? = nil,
        noonHour: Int? = nil,
        noonMinute: Int? = nil,
        eveningHour: Int? = nil,
        eveningMinute: Int? = nil,
        timezone: String? = nil,
        scheduleMorning: String? = nil,
        scheduleNoon: String? = nil,
        scheduleEvening: String? = nil,
        clientUpdatedAt: String? = nil
    ) {
        self.minWordCount = minWordCount
        self.morningHour = morningHour
        self.morningMinute = morningMinute
        self.noonHour = noonHour
        self.noonMinute = noonMinute
        self.eveningHour = eveningHour
        self.eveningMinute = eveningMinute
        self.timezone = timezone
        self.scheduleMorning = scheduleMorning
        self.scheduleNoon = scheduleNoon
        self.scheduleEvening = scheduleEvening
        self.clientUpdatedAt = clientUpdatedAt
    }

    enum CodingKeys: String, CodingKey {
        case minWordCount = "min_word_count"
        case morningHour = "morning_hour"
        case morningMinute = "morning_minute"
        case noonHour = "noon_hour"
        case noonMinute = "noon_minute"
        case eveningHour = "evening_hour"
        case eveningMinute = "evening_minute"
        case timezone
        case scheduleMorning = "schedule_morning"
        case scheduleNoon = "schedule_noon"
        case scheduleEvening = "schedule_evening"
        case clientUpdatedAt = "client_updated_at"
    }
}

// MARK: - Date Formatting Helper

extension ISO8601DateFormatter {
    /// Flexible formatter that handles various ISO 8601 formats
    static let flexibleFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    
    /// Formatter without fractional seconds
    static let basicFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}

public extension String {
    /// Parse ISO 8601 date string to Date
    /// Handles formats from Python's datetime.isoformat() and standard ISO8601:
    ///   "2026-01-27T15:02:00.000000"   (Python isoformat with microseconds, no Z)
    ///   "2026-01-27T15:02:00"          (Python isoformat without fractional seconds)
    ///   "2026-01-27T15:02:00.000Z"     (ISO8601 with fractional seconds + Z)
    ///   "2026-01-27T15:02:00Z"         (ISO8601 with Z)
    ///   "2026-01-27 15:02:00"          (SQLite format)
    func toISO8601Date() -> Date? {
        // Try strict ISO8601 with timezone first (Z or +00:00)
        ISO8601DateFormatter.flexibleFormatter.date(from: self)
            ?? ISO8601DateFormatter.basicFormatter.date(from: self)
            // Python isoformat: "2026-01-27T15:02:00.000000" (no timezone suffix)
            ?? DateFormatter.pythonISOWithMicroseconds.date(from: self)
            ?? DateFormatter.pythonISOWithMilliseconds.date(from: self)
            ?? DateFormatter.pythonISO.date(from: self)
            // SQLite: "2026-01-27 15:02:00"
            ?? DateFormatter.sqliteDateFormatter.date(from: self)
            ?? DateFormatter.sqliteDateFormatterWithMS.date(from: self)
    }
}

extension DateFormatter {
    /// Handles "2026-01-27T15:02:00.000000" (Python isoformat with microseconds)
    static let pythonISOWithMicroseconds: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Handles "2026-01-27T15:02:00.000" (with milliseconds)
    static let pythonISOWithMilliseconds: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Handles "2026-01-27T15:02:00" (no fractional seconds, no timezone)
    static let pythonISO: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Handles "2026-01-27 15:02:00" (SQLite / Python default)
    static let sqliteDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()

    /// Handles "2026-01-27 15:02:00.000000"
    static let sqliteDateFormatterWithMS: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSSSSS"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter
    }()
}
