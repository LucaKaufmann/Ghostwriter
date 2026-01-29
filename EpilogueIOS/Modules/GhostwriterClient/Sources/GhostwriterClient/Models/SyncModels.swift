//
//  SyncModels.swift
//  Epilogue
//
//  Combined sync response models for the GET /sync endpoint.
//

import Foundation

/// Combined sync response containing all data the client needs in one call.
public struct SyncResponse: Codable, Sendable {
    public let config: ClientConfigResponse
    public let feeds: FeedChangesResponse
    public let digests: SyncDigestsSection
    public let schedules: [ScheduleResponse]
}

/// Digests section of the sync response.
public struct SyncDigestsSection: Codable, Sendable {
    public let newDigests: [SyncDigest]

    enum CodingKeys: String, CodingKey {
        case newDigests = "new_digests"
    }
}

/// Digest with embedded articles from the sync endpoint.
public struct SyncDigest: Codable, Sendable, Identifiable {
    public let id: String
    public let filename: String
    public let period: String
    public let status: String
    public let stage: String?
    public let articleCount: Int
    public let errorMessage: String?
    public let createdAt: String
    public let completedAt: String?
    public let articles: [DigestArticleResponse]

    enum CodingKeys: String, CodingKey {
        case id, filename, period, status, stage, articles
        case articleCount = "article_count"
        case errorMessage = "error_message"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }
}
