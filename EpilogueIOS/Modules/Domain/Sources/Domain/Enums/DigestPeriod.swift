//
//  DigestPeriod.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Represents the time periods when a digest can be generated.
/// Users can select multiple periods for daily digest generation.
public enum DigestPeriod: String, Codable, CaseIterable, Sendable {
    case morning = "MORNING"
    case noon = "NOON"
    case evening = "EVENING"

    /// The hour of day (0-23) when the digest generation starts
    public var hour: Int {
        switch self {
        case .morning: return 7
        case .noon: return 12
        case .evening: return 18
        }
    }

    /// Default minute (0)
    public var minute: Int { 0 }

    /// User-friendly display name
    public var displayName: String {
        switch self {
        case .morning: return "Morning"
        case .noon: return "Noon"
        case .evening: return "Evening"
        }
    }

    /// User-friendly display time
    public var displayTime: String {
        String(format: "%d:%02d", hour, minute)
    }

    /// Icon name for SF Symbols
    public var iconName: String {
        switch self {
        case .morning: return "sunrise.fill"
        case .noon: return "sun.max.fill"
        case .evening: return "sunset.fill"
        }
    }

    /// Returns the period closest to the given hour
    public static func fromHour(_ hour: Int) -> DigestPeriod {
        switch hour {
        case ..<10: return .morning
        case ..<17: return .noon
        default: return .evening
        }
    }

    /// Server period string (lowercase)
    public var serverPeriod: String {
        rawValue.lowercased()
    }
}
