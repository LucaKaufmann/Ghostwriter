//
//  HealthModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Health check response from Ghostwriter
public struct HealthResponse: Codable, Sendable {
    public let status: String
    public let version: String
    public let uptimeSeconds: Int?
    public let lastSuccessfulDigest: String?
    public let aiProvider: String
    public let aiModel: String
    
    enum CodingKeys: String, CodingKey {
        case status, version
        case uptimeSeconds = "uptime_seconds"
        case lastSuccessfulDigest = "last_successful_digest"
        case aiProvider = "ai_provider"
        case aiModel = "ai_model"
    }
    
    /// Whether the service is healthy
    public var isHealthy: Bool {
        status == "ok" || status == "healthy"
    }
    
    /// Formatted uptime string
    public var formattedUptime: String? {
        guard let seconds = uptimeSeconds else { return nil }
        
        let hours = seconds / 3600
        let minutes = (seconds % 3600) / 60
        
        if hours > 24 {
            let days = hours / 24
            return "\(days)d \(hours % 24)h"
        } else if hours > 0 {
            return "\(hours)h \(minutes)m"
        } else {
            return "\(minutes)m"
        }
    }
}
