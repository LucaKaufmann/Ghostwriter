//
//  AIServiceProtocol.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Protocol defining AI summarization operations.
/// This protocol allows for multiple AI service implementations (OpenAI, Anthropic, Apple Intelligence).
public protocol AIServiceProtocol: Sendable {
    /// The provider type for this service
    var provider: AIProvider { get }

    /// Summarizes article content into a briefing format
    /// - Parameters:
    ///   - title: Article title
    ///   - content: Full article content (HTML or plain text)
    ///   - author: Article author (optional)
    /// - Returns: Summarized content in Markdown format with:
    ///   - Hook (1-2 sentences)
    ///   - Key Details (bulleted list)
    ///   - Significance (1-2 sentences)
    func summarize(title: String, content: String, author: String?) async throws -> String

    /// Validates that the service is properly configured and accessible
    /// - Returns: True if the service can be used, false otherwise
    func validateConfiguration() async throws -> Bool
}

/// Errors that can occur during AI operations
public enum AIServiceError: LocalizedError, Sendable {
    case missingAPIKey
    case invalidAPIKey
    case networkError(String)
    case rateLimitExceeded
    case contentTooLong
    case invalidResponse
    case serviceUnavailable

    public var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "API key is not configured"
        case .invalidAPIKey:
            return "API key is invalid or expired"
        case .networkError(let message):
            return "Network error: \(message)"
        case .rateLimitExceeded:
            return "Rate limit exceeded. Please try again later."
        case .contentTooLong:
            return "Article content is too long for summarization"
        case .invalidResponse:
            return "Received invalid response from AI service"
        case .serviceUnavailable:
            return "AI service is currently unavailable"
        }
    }
}
