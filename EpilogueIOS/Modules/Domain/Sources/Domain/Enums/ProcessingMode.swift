//
//  ProcessingMode.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Defines how articles from a feed should be processed.
public enum ProcessingMode: String, Codable, CaseIterable, Sendable {
    /// Full article extraction using content extraction algorithms.
    /// Preserves original structure, strips ads/sidebars.
    case fidelity = "FIDELITY"

    /// AI-powered summarization using OpenAI or other AI services.
    /// Generates concise briefings with hook, key details, and significance.
    case briefing = "BRIEFING"

    /// Human-readable display name
    public var displayName: String {
        switch self {
        case .fidelity:
            return "Deep Dive"
        case .briefing:
            return "Briefing"
        }
    }

    /// Description of the processing mode
    public var description: String {
        switch self {
        case .fidelity:
            return "Full article extraction with original content preserved"
        case .briefing:
            return "AI-generated summary with key points and significance"
        }
    }
}
