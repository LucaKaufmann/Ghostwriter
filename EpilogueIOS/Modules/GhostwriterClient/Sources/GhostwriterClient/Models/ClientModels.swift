//
//  ClientModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Heartbeat

/// Response from heartbeat endpoint
public struct HeartbeatResponse: Codable, Sendable {
    public let status: String
    public let receivedAt: String
    public let schedulesActive: Bool
    public let message: String?
    
    enum CodingKeys: String, CodingKey {
        case status
        case receivedAt = "received_at"
        case schedulesActive = "schedules_active"
        case message
    }
}

// MARK: - Client Status

/// Full client status response
public struct ClientStatusResponse: Codable, Sendable {
    public let lastHeartbeatAt: String?
    public let lastDownloadAt: String?
    public let lastFeedSyncAt: String?
    public let autoDisableEnabled: Bool
    public let autoDisableAfterDays: Int
    public let schedulesAutoDisabled: Bool
    public let autoDisabledAt: String?
    public let daysUntilAutoDisable: Int?
    
    enum CodingKeys: String, CodingKey {
        case lastHeartbeatAt = "last_heartbeat_at"
        case lastDownloadAt = "last_download_at"
        case lastFeedSyncAt = "last_feed_sync_at"
        case autoDisableEnabled = "auto_disable_enabled"
        case autoDisableAfterDays = "auto_disable_after_days"
        case schedulesAutoDisabled = "schedules_auto_disabled"
        case autoDisabledAt = "auto_disabled_at"
        case daysUntilAutoDisable = "days_until_auto_disable"
    }
    
    /// Whether schedules are currently active (not auto-disabled)
    public var areSchedulesActive: Bool {
        !schedulesAutoDisabled
    }
}

// MARK: - Schedule

/// Schedule response from Ghostwriter
public struct ScheduleResponse: Codable, Sendable, Identifiable {
    public let id: String
    public let period: String  // "morning", "noon", "evening"
    public let hour: Int
    public let minute: Int
    public let enabled: Bool
    public let timezone: String
    public let nextRunAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id, period, hour, minute, enabled, timezone
        case nextRunAt = "next_run_at"
    }
    
    /// Formatted time string (e.g., "07:00")
    public var formattedTime: String {
        String(format: "%02d:%02d", hour, minute)
    }
}

/// Request to update a schedule
public struct ScheduleUpdateRequest: Codable, Sendable {
    public let hour: Int?
    public let minute: Int?
    public let enabled: Bool?
    public let timezone: String?
    
    public init(hour: Int? = nil, minute: Int? = nil, enabled: Bool? = nil, timezone: String? = nil) {
        self.hour = hour
        self.minute = minute
        self.enabled = enabled
        self.timezone = timezone
    }
}
