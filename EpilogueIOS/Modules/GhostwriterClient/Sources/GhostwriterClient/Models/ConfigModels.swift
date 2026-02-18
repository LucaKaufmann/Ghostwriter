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

/// Media feed summary (podcast or YouTube feed).
public struct MediaFeedResponse: Codable, Sendable {
    public let id: String
    public let feedType: String
    public let url: String
    public let resolvedFeedURL: String?
    public let title: String
    public let isActive: Bool
    public let mode: String
    public let maxItems: Int
    public let createdAt: String
    public let updatedAt: String
    public let deletedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case feedType = "feed_type"
        case url
        case resolvedFeedURL = "resolved_feed_url"
        case title
        case isActive = "is_active"
        case mode
        case maxItems = "max_items"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case deletedAt = "deleted_at"
    }
}

/// Request model for creating a media feed.
public struct MediaFeedCreateRequest: Codable, Sendable {
    public let feedType: String
    public let url: String
    public let resolvedFeedURL: String?
    public let title: String
    public let isActive: Bool
    public let mode: String
    public let maxItems: Int

    public init(
        feedType: String,
        url: String,
        resolvedFeedURL: String? = nil,
        title: String,
        isActive: Bool = true,
        mode: String = "raw",
        maxItems: Int = 5
    ) {
        self.feedType = feedType
        self.url = url
        self.resolvedFeedURL = resolvedFeedURL
        self.title = title
        self.isActive = isActive
        self.mode = mode
        self.maxItems = maxItems
    }

    enum CodingKeys: String, CodingKey {
        case feedType = "feed_type"
        case url
        case resolvedFeedURL = "resolved_feed_url"
        case title
        case isActive = "is_active"
        case mode
        case maxItems = "max_items"
    }
}

/// Request model for partially updating a media feed.
public struct MediaFeedUpdateRequest: Codable, Sendable {
    public let title: String?
    public let isActive: Bool?
    public let mode: String?
    public let maxItems: Int?

    public init(
        title: String? = nil,
        isActive: Bool? = nil,
        mode: String? = nil,
        maxItems: Int? = nil
    ) {
        self.title = title
        self.isActive = isActive
        self.mode = mode
        self.maxItems = maxItems
    }

    enum CodingKeys: String, CodingKey {
        case title
        case isActive = "is_active"
        case mode
        case maxItems = "max_items"
    }
}

/// Request model for resolving a YouTube channel URL.
public struct YouTubeResolveRequest: Codable, Sendable {
    public let url: String

    public init(url: String) {
        self.url = url
    }
}

/// Response model from YouTube URL resolve endpoint.
public struct YouTubeResolveResponse: Codable, Sendable {
    public let rssFeedURL: String
    public let channelID: String
    public let channelTitle: String?

    enum CodingKeys: String, CodingKey {
        case rssFeedURL = "rss_feed_url"
        case channelID = "channel_id"
        case channelTitle = "channel_title"
    }
}

/// Media processing queue status.
public struct MediaProcessingStatusResponse: Codable, Sendable {
    public let isRunning: Bool
    public let pendingCount: Int
    public let processingCount: Int
    public let completedCount: Int
    public let failedCount: Int
    public let currentItemTitle: String?
    public let currentItemContentType: String?
    public let lastCompletedAt: String?
    public let nextRunAt: String?

    enum CodingKeys: String, CodingKey {
        case isRunning = "is_running"
        case pendingCount = "pending_count"
        case processingCount = "processing_count"
        case completedCount = "completed_count"
        case failedCount = "failed_count"
        case currentItemTitle = "current_item_title"
        case currentItemContentType = "current_item_content_type"
        case lastCompletedAt = "last_completed_at"
        case nextRunAt = "next_run_at"
    }
}

/// Response for manually triggering media processing.
public struct MediaTriggerResponse: Codable, Sendable {
    public let status: String
    public let detail: String?
}

/// Media item summary without full transcript content.
public struct MediaItemSummaryResponse: Codable, Sendable {
    public let id: String
    public let mediaFeedID: String
    public let title: String
    public let author: String?
    public let contentType: String
    public let mode: String
    public let wordCount: Int
    public let isSummary: Bool
    public let aiFailed: Bool
    public let status: String
    public let errorMessage: String?
    public let consumedAt: String?
    public let createdAt: String
    public let completedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case mediaFeedID = "media_feed_id"
        case title
        case author
        case contentType = "content_type"
        case mode
        case wordCount = "word_count"
        case isSummary = "is_summary"
        case aiFailed = "ai_failed"
        case status
        case errorMessage = "error_message"
        case consumedAt = "consumed_at"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }
}

/// Full media item payload including transcript/content body.
public struct MediaItemResponse: Codable, Sendable {
    public let id: String
    public let mediaFeedID: String
    public let guid: String
    public let url: String
    public let contentURL: String?
    public let title: String
    public let author: String?
    public let content: String
    public let contentType: String
    public let mode: String
    public let wordCount: Int
    public let isSummary: Bool
    public let aiFailed: Bool
    public let processingMs: Int
    public let status: String
    public let errorMessage: String?
    public let consumedAt: String?
    public let consumedDigestID: String?
    public let createdAt: String
    public let completedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case mediaFeedID = "media_feed_id"
        case guid
        case url
        case contentURL = "content_url"
        case title
        case author
        case content
        case contentType = "content_type"
        case mode
        case wordCount = "word_count"
        case isSummary = "is_summary"
        case aiFailed = "ai_failed"
        case processingMs = "processing_ms"
        case status
        case errorMessage = "error_message"
        case consumedAt = "consumed_at"
        case consumedDigestID = "consumed_digest_id"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }
}

/// Server log file metadata.
public struct LogFileInfoResponse: Codable, Sendable {
    public let filename: String
    public let sizeBytes: Int64
    public let modifiedAt: String

    enum CodingKeys: String, CodingKey {
        case filename
        case sizeBytes = "size_bytes"
        case modifiedAt = "modified_at"
    }
}

/// Auth API token model from /auth/tokens list endpoint.
public struct AuthAPITokenResponse: Codable, Sendable {
    public let id: String
    public let name: String
    public let tokenPrefix: String
    public let createdAt: String
    public let lastUsedAt: String?
    public let revokedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case tokenPrefix = "token_prefix"
        case createdAt = "created_at"
        case lastUsedAt = "last_used_at"
        case revokedAt = "revoked_at"
    }
}

/// Request model for creating an auth API token.
public struct AuthAPITokenCreateRequest: Codable, Sendable {
    public let name: String

    public init(name: String) {
        self.name = name
    }
}

/// Response model for creating an auth API token.
public struct AuthAPITokenCreateResponse: Codable, Sendable {
    public let id: String
    public let name: String
    public let token: String
    public let tokenPrefix: String
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case token
        case tokenPrefix = "token_prefix"
        case createdAt = "created_at"
    }
}

/// Generic status/message response.
public struct StatusMessageResponse: Codable, Sendable {
    public let status: String
    public let message: String?
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
    public let pdfEnabled: Bool?
    public let pdfPageSize: String?
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
        case pdfEnabled = "pdf_enabled"
        case pdfPageSize = "pdf_page_size"
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
    public let includePodcastsInDigest: Bool?
    public let includeYoutubeInDigest: Bool?
    public let pdfEnabled: Bool?
    public let pdfPageSize: String?
    public let coverEnabled: Bool?
    public let coverProvider: String?
    public let coverQuality: String?
    public let coverPrompt: String?
    public let coverOverlayEnabled: Bool?
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
        includePodcastsInDigest: Bool? = nil,
        includeYoutubeInDigest: Bool? = nil,
        pdfEnabled: Bool? = nil,
        pdfPageSize: String? = nil,
        coverEnabled: Bool? = nil,
        coverProvider: String? = nil,
        coverQuality: String? = nil,
        coverPrompt: String? = nil,
        coverOverlayEnabled: Bool? = nil,
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
        self.includePodcastsInDigest = includePodcastsInDigest
        self.includeYoutubeInDigest = includeYoutubeInDigest
        self.pdfEnabled = pdfEnabled
        self.pdfPageSize = pdfPageSize
        self.coverEnabled = coverEnabled
        self.coverProvider = coverProvider
        self.coverQuality = coverQuality
        self.coverPrompt = coverPrompt
        self.coverOverlayEnabled = coverOverlayEnabled
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
        case includePodcastsInDigest = "include_podcasts_in_digest"
        case includeYoutubeInDigest = "include_youtube_in_digest"
        case pdfEnabled = "pdf_enabled"
        case pdfPageSize = "pdf_page_size"
        case coverEnabled = "cover_enabled"
        case coverProvider = "cover_provider"
        case coverQuality = "cover_quality"
        case coverPrompt = "cover_prompt"
        case coverOverlayEnabled = "cover_overlay_enabled"
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
