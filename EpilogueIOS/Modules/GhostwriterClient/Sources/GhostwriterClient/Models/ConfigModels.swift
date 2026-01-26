//
//  ConfigModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Response Models

/// Response model for client configuration (shared settings)
public struct ClientConfigResponse: Codable, Sendable {
    public let minWordCount: Int
    public let morningHour: Int
    public let morningMinute: Int
    public let noonHour: Int
    public let noonMinute: Int
    public let eveningHour: Int
    public let eveningMinute: Int
    public let timezone: String
    public let updatedAt: String
    
    enum CodingKeys: String, CodingKey {
        case minWordCount = "min_word_count"
        case morningHour = "morning_hour"
        case morningMinute = "morning_minute"
        case noonHour = "noon_hour"
        case noonMinute = "noon_minute"
        case eveningHour = "evening_hour"
        case eveningMinute = "evening_minute"
        case timezone
        case updatedAt = "updated_at"
    }
    
    /// Parse the updatedAt timestamp to a Date
    public func parsedUpdatedAt() -> Date? {
        ISO8601DateFormatter.flexibleFormatter.date(from: updatedAt)
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

extension String {
    /// Parse ISO 8601 date string to Date
    func toISO8601Date() -> Date? {
        ISO8601DateFormatter.flexibleFormatter.date(from: self)
            ?? ISO8601DateFormatter.basicFormatter.date(from: self)
    }
}
