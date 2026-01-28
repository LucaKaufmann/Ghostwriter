//
//  ArticleRepository.swift
//  Epilogue
//
//  Created on 2026-01-26.
//  Copyright © 2026 Epilogue. All rights reserved.
//

import Foundation
import Domain

/// Implementation of ArticleRepositoryProtocol that orchestrates feed parsing,
/// content extraction, and AI summarization
public final class ArticleRepository: ArticleRepositoryProtocol {
    private let feedParser: FeedParserProtocol
    private let contentExtractor: ContentExtractorProtocol
    private let aiService: AIServiceProtocol?
    private let minWordCount: Int

    public init(
        feedParser: FeedParserProtocol,
        contentExtractor: ContentExtractorProtocol,
        aiService: AIServiceProtocol? = nil,
        minWordCount: Int = 300
    ) {
        self.feedParser = feedParser
        self.contentExtractor = contentExtractor
        self.aiService = aiService
        self.minWordCount = minWordCount
    }

    public func fetchAndProcessArticles() async throws -> [ProcessedArticle] {
        // This would need access to FeedRepository to get enabled feeds
        // For now, return empty array - this will be properly implemented
        // when we wire up dependencies
        return []
    }

    public func fetchAndProcessArticles(from feed: Feed) async throws -> [ProcessedArticle] {
        // Fetch raw articles from feed
        let rawArticles = try await fetchFeedArticles(feedUrl: feed.url)

        // Apply maxArticles limit if set
        let articlesToProcess = feed.maxArticles > 0
            ? Array(rawArticles.prefix(feed.maxArticles))
            : rawArticles

        // Process articles in parallel
        return try await withThrowingTaskGroup(of: ProcessedArticle?.self) { group in
            for article in articlesToProcess {
                group.addTask {
                    try? await self.processArticle(article, mode: feed.mode)
                }
            }

            var processed: [ProcessedArticle] = []
            for try await result in group {
                if let article = result {
                    processed.append(article)
                }
            }
            return processed
        }
    }

    public func fetchFeedArticles(feedUrl: String) async throws -> [RawArticle] {
        try await feedParser.parseFeed(url: feedUrl, feedName: "")
    }

    public func processArticle(_ article: RawArticle, mode: ProcessingMode) async throws -> ProcessedArticle {
        switch mode {
        case .fidelity:
            return try await processFidelityMode(article)
        case .briefing:
            return try await processBriefingMode(article)
        }
    }

    public func extractFullContent(url: String) async throws -> String {
        try await contentExtractor.extractContent(from: url)
    }

    public func validateFeedUrl(_ url: String) async throws -> Bool {
        try await feedParser.validateFeedURL(url)
    }

    // MARK: - Private Helpers

    private func processFidelityMode(_ article: RawArticle) async throws -> ProcessedArticle {
        // Extract full content
        let content = try await contentExtractor.extractContent(from: article.link)

        // Check word count filter
        let wordCount = contentExtractor.countWords(in: content)
        guard wordCount >= minWordCount else {
            throw ArticleProcessingError.contentTooShort
        }

        return ProcessedArticle(
            title: article.title,
            author: article.author,
            content: content,
            originalUrl: article.link,
            feedUrl: article.feedUrl,
            feedName: article.feedName,
            isSummary: false,
            publishedAt: article.publishedAt,
            wordCount: wordCount
        )
    }

    private func processBriefingMode(_ article: RawArticle) async throws -> ProcessedArticle {
        guard let aiService = aiService else {
            throw ArticleProcessingError.aiServiceUnavailable
        }

        // Extract full content first
        let fullContent = try await contentExtractor.extractContent(from: article.link)

        // Generate summary
        let summary = try await aiService.summarize(
            title: article.title,
            content: fullContent,
            author: article.author.isEmpty ? nil : article.author
        )

        let wordCount = contentExtractor.countWords(in: summary)

        return ProcessedArticle(
            title: article.title,
            author: article.author,
            content: summary,
            originalUrl: article.link,
            feedUrl: article.feedUrl,
            feedName: article.feedName,
            isSummary: true,
            publishedAt: article.publishedAt,
            wordCount: wordCount
        )
    }
}

// MARK: - Errors

public enum ArticleProcessingError: LocalizedError {
    case contentTooShort
    case aiServiceUnavailable

    public var errorDescription: String? {
        switch self {
        case .contentTooShort:
            return "Article content does not meet minimum word count"
        case .aiServiceUnavailable:
            return "AI service is not configured for briefing mode"
        }
    }
}
