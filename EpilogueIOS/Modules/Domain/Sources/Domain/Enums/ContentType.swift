//
//  ContentType.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Defines the type of content in a digest article.
public enum ContentType: String, Codable, CaseIterable, Sendable {
    /// AI-generated briefing/summary
    case briefing = "BRIEFING"

    /// Full article content extracted from source
    case deepDive = "DEEP_DIVE"

    /// Human-readable display name
    public var displayName: String {
        switch self {
        case .briefing:
            return "Briefing"
        case .deepDive:
            return "Deep Dive"
        }
    }

    /// EPUB section name for this content type
    public var sectionName: String {
        switch self {
        case .briefing:
            return "Briefings"
        case .deepDive:
            return "Deep Dives"
        }
    }

    /// Order in which this content type should appear in digest
    public var sortOrder: Int {
        switch self {
        case .briefing:
            return 0
        case .deepDive:
            return 1
        }
    }
}
