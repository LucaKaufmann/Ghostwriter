//
//  TriggerType.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Defines how a digest generation was triggered.
public enum TriggerType: String, Codable, CaseIterable, Sendable {
    /// Digest was generated automatically by the scheduled background task
    case scheduled = "SCHEDULED"

    /// Digest was generated manually by the user via "Run Now" button
    case manual = "MANUAL"

    /// Digest was generated as part of app testing or development
    case test = "TEST"

    /// Digest was synced from Ghostwriter server
    case ghostwriter = "GHOSTWRITER"

    /// Human-readable display name
    public var displayName: String {
        switch self {
        case .scheduled:
            return "Scheduled"
        case .manual:
            return "Manual"
        case .test:
            return "Test"
        case .ghostwriter:
            return "Ghostwriter"
        }
    }

    /// Icon name for SF Symbols
    public var iconName: String {
        switch self {
        case .scheduled:
            return "clock.arrow.circlepath"
        case .manual:
            return "hand.tap"
        case .test:
            return "testtube.2"
        case .ghostwriter:
            return "cloud.fill"
        }
    }
}
