//
//  ProcessedArticle.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Represents a transient article that has been fetched and processed,
/// but not yet persisted to a digest. This is used in the processing pipeline.
public struct ProcessedArticle: Sendable {
    /// Article title
    public let title: String

    /// Article author (may be empty)
    public let author: String

    /// Processed content (HTML or Markdown)
    public let content: String

    /// Original article URL
    public let originalUrl: String

    /// Source feed URL
    public let feedUrl: String

    /// Source feed name
    public let feedName: String

    /// Whether this is an AI-generated summary
    public let isSummary: Bool

    /// Timestamp when the article was published (if available)
    public let publishedAt: Date?

    /// Word count of the processed content
    public let wordCount: Int

    public init(
        title: String,
        author: String = "",
        content: String,
        originalUrl: String,
        feedUrl: String,
        feedName: String,
        isSummary: Bool,
        publishedAt: Date? = nil,
        wordCount: Int = 0
    ) {
        self.title = title
        self.author = author
        self.content = content
        self.originalUrl = originalUrl
        self.feedUrl = feedUrl
        self.feedName = feedName
        self.isSummary = isSummary
        self.publishedAt = publishedAt
        self.wordCount = wordCount
    }

    /// Converts this transient model to a DigestArticle for persistence
    public func toDigestArticle(contentType: ContentType, orderIndex: Int) -> DigestArticle {
        DigestArticle(
            title: title,
            author: author,
            content: content,
            originalUrl: originalUrl,
            feedUrl: feedUrl,
            feedName: feedName,
            contentType: contentType,
            publishedAt: publishedAt,
            orderIndex: orderIndex,
            wordCount: wordCount
        )
    }
}
