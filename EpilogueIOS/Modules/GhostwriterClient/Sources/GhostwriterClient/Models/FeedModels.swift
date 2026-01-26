//
//  FeedModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Request Models

/// Request model for syncing feeds to the server
public struct FeedSyncRequest: Codable, Sendable {
    public let url: String
    public let title: String
    public let isActive: Bool
    public let mode: String  // "raw" or "summarize"
    public let maxArticles: Int
    
    public init(url: String, title: String, isActive: Bool = true, mode: String = "raw", maxArticles: Int = 10) {
        self.url = url
        self.title = title
        self.isActive = isActive
        self.mode = mode
        self.maxArticles = maxArticles
    }
    
    enum CodingKeys: String, CodingKey {
        case url, title, mode
        case isActive = "is_active"
        case maxArticles = "max_articles"
    }
}

// MARK: - Response Models

/// Response model for feed sync operation
public struct FeedSyncResponse: Codable, Sendable {
    public let synced: Int
    public let created: Int
    public let updated: Int
    public let unchanged: Int
}

/// Feed response model from Ghostwriter
public struct FeedResponse: Codable, Sendable, Identifiable {
    public let id: String
    public let url: String
    public let title: String
    public let isActive: Bool
    public let mode: String
    public let maxArticles: Int
    public let createdAt: String
    public let updatedAt: String
    public let deletedAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id, url, title, mode
        case isActive = "is_active"
        case maxArticles = "max_articles"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case deletedAt = "deleted_at"
    }
}

/// Tombstone for a deleted feed (from server)
public struct FeedTombstone: Codable, Sendable {
    public let url: String
    public let deletedAt: String
    
    enum CodingKeys: String, CodingKey {
        case url
        case deletedAt = "deleted_at"
    }
}

/// Response for feed changes (incremental sync)
public struct FeedChangesResponse: Codable, Sendable {
    public let feeds: [FeedResponse]
    public let tombstones: [FeedTombstone]
    public let serverTimestamp: String
    
    enum CodingKeys: String, CodingKey {
        case feeds, tombstones
        case serverTimestamp = "server_timestamp"
    }
}
