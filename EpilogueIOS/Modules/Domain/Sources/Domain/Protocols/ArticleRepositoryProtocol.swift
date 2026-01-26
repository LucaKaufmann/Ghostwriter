//
//  ArticleRepositoryProtocol.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation

/// Protocol defining article fetching and processing operations.
/// This is the main orchestrator for the content pipeline.
public protocol ArticleRepositoryProtocol: Sendable {
    /// Fetches and processes articles from all enabled feeds
    /// Returns a list of processed articles ready for EPUB generation
    func fetchAndProcessArticles() async throws -> [ProcessedArticle]

    /// Fetches and processes articles from a specific feed
    func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle]

    /// Fetches raw articles from a feed URL (RSS/Atom parsing)
    func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle]

    /// Processes a single raw article according to its feed's processing mode
    func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle

    /// Extracts full article content from a URL (for FIDELITY mode)
    func extractFullContent(url: String) async throws -> String

    /// Validates if a feed URL is accessible and parseable
    func validateFeedUrl(_ url: String) async throws -> Bool
}

/// Represents a raw article fetched from an RSS/Atom feed before processing
public struct RawArticle: Sendable {
    public let title: String
    public let link: String
    public let author: String
    public let publishedAt: Date?
    public let feedUrl: String
    public let feedName: String

    public init(
        title: String,
        link: String,
        author: String = "",
        publishedAt: Date? = nil,
        feedUrl: String,
        feedName: String
    ) {
        self.title = title
        self.link = link
        self.author = author
        self.publishedAt = publishedAt
        self.feedUrl = feedUrl
        self.feedName = feedName
    }
}
