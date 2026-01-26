//
//  GhostwriterError.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Errors that can occur when interacting with the Ghostwriter API
public enum GhostwriterError: LocalizedError {
    /// Ghostwriter is not configured (missing URL or disabled)
    case notConfigured
    
    /// Invalid URL provided
    case invalidURL(String)
    
    /// Network request failed
    case networkError(Error)
    
    /// HTTP error with status code
    case httpError(statusCode: Int, message: String?)
    
    /// Failed to decode response
    case decodingError(Error)
    
    /// Failed to encode request
    case encodingError(Error)
    
    /// Conflict - resource was modified by another client
    case conflict(message: String)
    
    /// Digest generation already in progress
    case digestInProgress
    
    /// Resource not found
    case notFound(String)
    
    /// Authentication failed
    case unauthorized
    
    public var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "Ghostwriter is not configured"
        case .invalidURL(let url):
            return "Invalid URL: \(url)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .httpError(let statusCode, let message):
            if let message = message {
                return "HTTP \(statusCode): \(message)"
            }
            return "HTTP error \(statusCode)"
        case .decodingError(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .encodingError(let error):
            return "Failed to encode request: \(error.localizedDescription)"
        case .conflict(let message):
            return "Conflict: \(message)"
        case .digestInProgress:
            return "A digest is already being generated"
        case .notFound(let resource):
            return "Not found: \(resource)"
        case .unauthorized:
            return "Authentication failed"
        }
    }
}
