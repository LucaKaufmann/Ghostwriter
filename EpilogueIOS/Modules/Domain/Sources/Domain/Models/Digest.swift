//
//  Digest.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import SwiftData

/// Represents a generated daily digest with its metadata and file location.
/// This model is persisted using SwiftData.
@Model
public final class Digest {
    /// Unique identifier for the digest
    @Attribute(.unique) public var id: UUID

    /// Timestamp when the digest was generated
    public var generatedAt: Date

    /// File path to the generated EPUB file
    public var epubFilePath: String

    /// Number of articles included in the digest
    public var articleCount: Int

    /// Number of briefing articles in the digest
    public var briefingCount: Int

    /// Number of full-content articles in the digest
    public var deepDiveCount: Int

    /// How the digest was triggered
    public var triggerType: TriggerType

    /// Total size of the EPUB file in bytes
    public var fileSizeBytes: Int64

    /// Whether the digest generation completed successfully
    public var isComplete: Bool

    /// Error message if generation failed
    public var errorMessage: String?

    /// Relationship to articles in this digest
    @Relationship(deleteRule: .cascade, inverse: \DigestArticle.digest)
    public var articles: [DigestArticle]

    public init(
        id: UUID = UUID(),
        generatedAt: Date = Date(),
        epubFilePath: String,
        articleCount: Int = 0,
        briefingCount: Int = 0,
        deepDiveCount: Int = 0,
        triggerType: TriggerType,
        fileSizeBytes: Int64 = 0,
        isComplete: Bool = false,
        errorMessage: String? = nil,
        articles: [DigestArticle] = []
    ) {
        self.id = id
        self.generatedAt = generatedAt
        self.epubFilePath = epubFilePath
        self.articleCount = articleCount
        self.briefingCount = briefingCount
        self.deepDiveCount = deepDiveCount
        self.triggerType = triggerType
        self.fileSizeBytes = fileSizeBytes
        self.isComplete = isComplete
        self.errorMessage = errorMessage
        self.articles = articles
    }
}
