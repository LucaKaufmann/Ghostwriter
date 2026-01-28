//
//  DigestArticle.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData

/// Represents an article that has been processed and included in a digest.
/// This model is persisted using SwiftData.
@Model
public final class DigestArticle {
    /// Unique identifier for the digest article
    @Attribute(.unique) public var id: UUID

    /// The parent digest this article belongs to
    public var digest: Digest?

    /// Article title
    public var title: String

    /// Article author (may be empty)
    public var author: String

    /// Processed content (HTML or Markdown depending on processing mode)
    public var content: String

    /// Original article URL
    public var originalUrl: String

    /// Source feed URL
    public var feedUrl: String

    /// Source feed name
    public var feedName: String

    /// Type of content (briefing or deep dive)
    public var contentType: ContentType

    /// Timestamp when the article was published (if available)
    public var publishedAt: Date?

    /// Order/position in the digest (for sorting)
    public var orderIndex: Int

    /// Word count of the processed content
    public var wordCount: Int

    public init(
        id: UUID = UUID(),
        digest: Digest? = nil,
        title: String,
        author: String = "",
        content: String,
        originalUrl: String,
        feedUrl: String,
        feedName: String,
        contentType: ContentType,
        publishedAt: Date? = nil,
        orderIndex: Int = 0,
        wordCount: Int = 0
    ) {
        self.id = id
        self.digest = digest
        self.title = title
        self.author = author
        self.content = content
        self.originalUrl = originalUrl
        self.feedUrl = feedUrl
        self.feedName = feedName
        self.contentType = contentType
        self.publishedAt = publishedAt
        self.orderIndex = orderIndex
        self.wordCount = wordCount
    }
}
