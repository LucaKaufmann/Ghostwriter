//
//  DigestModels.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

// MARK: - Request Models

/// Request model for triggering a digest generation
public struct DigestTriggerRequest: Codable, Sendable {
    public let period: String  // "morning", "noon", "evening", "manual"
    
    public init(period: String = "manual") {
        self.period = period
    }
}

// MARK: - Response Models

/// Response from digest trigger
public struct DigestTriggerResponse: Codable, Sendable {
    public let id: String?
    public let status: String
    public let message: String
}

/// Digest progress information
public struct DigestProgress: Codable, Sendable {
    public let totalFeeds: Int
    public let feedsFetched: Int
    public let totalArticles: Int
    public let articlesEnriched: Int
    
    enum CodingKeys: String, CodingKey {
        case totalFeeds = "total_feeds"
        case feedsFetched = "feeds_fetched"
        case totalArticles = "total_articles"
        case articlesEnriched = "articles_enriched"
    }
    
    /// Progress percentage (0.0 - 1.0)
    public var progressPercentage: Double {
        guard totalArticles > 0 else { return 0 }
        return Double(articlesEnriched) / Double(totalArticles)
    }
}

/// Digest status response for polling
public struct DigestStatusResponse: Codable, Sendable {
    public let id: String
    public let status: String  // "queued", "processing", "completed", "failed"
    public let stage: String?  // "fetching", "extracting", "enriching", "compiling"
    public let progress: DigestProgress
    public let startedAt: String
    public let etaSeconds: Int?
    
    enum CodingKeys: String, CodingKey {
        case id, status, stage, progress
        case startedAt = "started_at"
        case etaSeconds = "eta_seconds"
    }
    
    /// Whether the digest job is complete (success or failure)
    public var isComplete: Bool {
        status == "completed" || status == "failed"
    }
    
    /// Whether the digest job succeeded
    public var isSuccessful: Bool {
        status == "completed"
    }
}

/// Digest list item response
public struct DigestResponse: Codable, Sendable, Identifiable {
    public let id: String
    public let filename: String
    public let period: String
    public let status: String
    public let stage: String?
    public let articleCount: Int
    public let errorMessage: String?
    public let createdAt: String
    public let completedAt: String?
    public let downloadedAt: String?
    
    enum CodingKeys: String, CodingKey {
        case id, filename, period, status, stage
        case articleCount = "article_count"
        case errorMessage = "error_message"
        case createdAt = "created_at"
        case completedAt = "completed_at"
        case downloadedAt = "downloaded_at"
    }
    
    /// Whether this digest is completed and ready for download
    public var isCompleted: Bool {
        status == "completed"
    }
}

/// Digest article with content - for syncing article content to the app
public struct DigestArticleResponse: Codable, Sendable, Identifiable {
    public let id: String
    public let title: String
    public let url: String
    public let mode: String
    public let wordCount: Int
    public let content: String
    public let author: String?
    public let feedTitle: String
    public let sortOrder: Int
    public let aiFailed: Bool
    
    enum CodingKeys: String, CodingKey {
        case id, title, url, mode, content, author
        case wordCount = "word_count"
        case feedTitle = "feed_title"
        case sortOrder = "sort_order"
        case aiFailed = "ai_failed"
    }
}

/// Response containing all articles for a digest
public struct DigestArticlesResponse: Codable, Sendable {
    public let digestId: String
    public let articleCount: Int
    public let articles: [DigestArticleResponse]
    
    enum CodingKeys: String, CodingKey {
        case digestId = "digest_id"
        case articleCount = "article_count"
        case articles
    }
}

/// Response for checking new digests
public struct NewDigestsResponse: Codable, Sendable {
    public let hasNew: Bool
    public let count: Int
    public let digests: [DigestResponse]
    
    enum CodingKeys: String, CodingKey {
        case hasNew = "has_new"
        case count, digests
    }
}
